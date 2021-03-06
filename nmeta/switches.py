# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#*** nmeta - Network Metadata - Abstractions of Switches for OpenFlow Calls

"""
This module is part of the nmeta suite running on top of Ryu SDN controller.

It provides classes that abstract the details of OpenFlow switches
"""

#*** General Imports:
import sys
import struct

#*** For timestamps:
import datetime

#*** Ryu Imports:
from ryu.lib import addrconv
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ipv4, ipv6
from ryu.lib.packet import tcp
from ryu.lib.packet import udp

#*** For logging configuration:
from baseclass import BaseClass

#*** mongodb Database Import:
import pymongo
from pymongo import MongoClient

#*** Constant to use for a port not found value:
PORT_NOT_FOUND = 999999999

#*** Supports OpenFlow version 1.3:
OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

class Switches(BaseClass):
    """
    This class provides an abstraction for a set of OpenFlow
    Switches.

    It stores instances of the Switch class in a dictionary keyed
    by DPID. The switch instances are accessible externally.

    A standard (not capped) MongoDB database collection is used to
    record switch details so that they can be accessed via the
    external API.
    """
    def __init__(self, config):
        #*** Required for BaseClass:
        self.config = config
        #*** Set up Logging with inherited base class method:
        self.configure_logging(__name__, "switches_logging_level_s",
                                       "switches_logging_level_c")

        #*** Set up database collections:
        #*** Get parameters from config:
        mongo_addr = config.get_value("mongo_addr")
        mongo_port = config.get_value("mongo_port")
        mongo_dbname = config.get_value("mongo_dbname")

        #*** Start mongodb:
        self.logger.info("Connecting to MongoDB database...")
        mongo_client = MongoClient(mongo_addr, mongo_port)

        #*** Connect to MongoDB nmeta database:
        db_nmeta = mongo_client[mongo_dbname]

        #*** Delete (drop) previous switches collection if it exists:
        self.logger.debug("Deleting previous switches MongoDB collection...")
        db_nmeta.switches_col.drop()

        #*** Create the switches collection:
        self.switches_col = db_nmeta.create_collection('switches_col')

        #*** Index dpid key to improve look-up performance:
        self.switches_col.create_index([('dpid', pymongo.TEXT)], unique=False)

        #*** Get max bytes of new flow packets to send to controller from
        #*** config file:
        self.miss_send_len = config.get_value("miss_send_len")
        if self.miss_send_len < 1500:
            self.logger.info("Be aware that setting "
                             "miss_send_len to less than a full size packet "
                             "may result in errors due to truncation. "
                             "Configured value is %s bytes",
                             self.miss_send_len)
        #*** Tell switch how to handle fragments (see OpenFlow spec):
        self.ofpc_frag = config.get_value("ofpc_frag")

        #*** Flow mod cookie value offset indicates flow session direction:
        self.offset = config.get_value("flow_mod_cookie_reverse_offset")

        #*** Dictionary of the instances of the Switch class,
        #***  key is the switch DPID which is assumed to be unique:
        self.switches = {}

    def add(self, datapath):
        """
        Add a switch to the Switches class
        """
        dpid = datapath.id
        self.logger.info("Adding switch dpid=%s", dpid)
        switch = Switch(self.config, datapath, self.offset)
        switch.dpid = dpid
        (ip_address, port) = datapath.address
        #*** Record class instance into dictionary to make it accessible:
        self.switches[datapath.id] = switch
        #*** Record switch in database collection:
        self.switches_col.update_one({'dpid': dpid},
                                {
                                "$set":
                                    {
                                    'dpid': dpid,
                                    'time_connected': datetime.datetime.now(),
                                    'ip_address': ip_address,
                                    'port': port
                                }
                        }, upsert=True)
        #*** Set the switch up for operation:
        switch.set_switch_config(self.ofpc_frag, self.miss_send_len)
        switch.request_switch_desc()
        switch.set_switch_table_miss(self.miss_send_len)
        return 1

    def stats_reply(self, msg):
        """
        Read in a switch stats reply
        """
        body = msg.body
        dpid = msg.datapath.id
        #*** Look up the switch:
        if dpid in self.switches:
            self.logger.info('event=DescStats Switch dpid=%s is mfr_desc="%s" '
                      'hw_desc="%s" sw_desc="%s" serial_num="%s" dp_desc="%s"',
                      dpid, body.mfr_desc, body.hw_desc, body.sw_desc,
                      body.serial_num, body.dp_desc)
            switch = self.switches[dpid]
            switch.mfr_desc = body.mfr_desc
            switch.hw_desc = body.hw_desc
            switch.sw_desc = body.sw_desc
            switch.serial_num = body.serial_num
            switch.dp_desc = body.dp_desc

            #*** Update switch details in database collection:
            self.switches_col.update_one({'dpid': dpid},
                                {
                                "$set":
                                    {
                                    'dpid': dpid,
                                    'mfr_desc': switch.mfr_desc,
                                    'hw_desc': switch.hw_desc,
                                    'sw_desc': switch.sw_desc,
                                    'serial_num': switch.serial_num,
                                    'dp_desc': switch.dp_desc
                                }
                        }, upsert=True)
        else:
            self.logger.warning("Ignoring DescStats reply from unknown switch"
                                                              " dpid=%s", dpid)
            return 0

    def __getitem__(self, key):
        """
        Passed a dpid key and return corresponding switch
        object, or 0 if it doesn't exist.
        Example:
            switch = switches[dpid]
        """
        if key in self.switches:
            return self.switches[key]
        else:
            return 0

    def delete(self, datapath):
        """
        Delete a switch from the Switches class
        """
        dpid = datapath.id
        self.logger.info("Deleting switch dpid=%s", dpid)
        #*** Get relevant instance of switch class:
        if not dpid in self.switches:
            return 0
        #*** Delete from dictionary of switches:
        del self.switches[dpid]
        #*** Delete switch from database collection:
        self.switches_col.delete_one({'dpid': dpid})
        return 1

class Switch(BaseClass):
    """
    This class provides an abstraction for an OpenFlow
    Switch
    """
    def __init__(self, config, datapath, offset):
        #*** Required for BaseClass:
        self.config = config
        #*** Set up Logging with inherited base class method:
        self.configure_logging(__name__, "switches_logging_level_s",
                                       "switches_logging_level_c")
        #*** Initialise switch variables:
        self.config = config
        self.datapath = datapath
        self.switch_hash = ""
        self.dpid = 0
        self.ip_address = ""
        self.time = ""
        self.cxn_status = ""
        self.cxn_ver = ""
        self.mfr_desc = ""
        self.hw_desc = ""
        self.sw_desc = ""
        self.serial_num = ""
        self.dp_desc = ""
        #*** Instantiate a class that represents flow tables:
        self.flowtables = FlowTables(config, datapath, offset)

    def dbdict(self):
        """
        Return a dictionary object of switch
        parameters for storing in the database
        """
        return self.__dict__

    def request_switch_desc(self):
        """
        Send an OpenFlow request to the switch asking it to
        send us it's description data
        """
        parser = self.datapath.ofproto_parser
        req = parser.OFPDescStatsRequest(self.datapath, 0)
        self.logger.debug("Sending description request to dpid=%s",
                            self.datapath.id)
        self.datapath.send_msg(req)

    def set_switch_config(self, config_flags, miss_send_len):
        """
        Set config on a switch including config flags that
        instruct fragment handling behaviour and miss_send_len
        which controls the number of bytes sent to the controller
        when the output port is specified as the controller.
        """
        parser = self.datapath.ofproto_parser
        self.logger.info("Setting config on switch "
                         "dpid=%s to config_flags flag=%s and "
                         "miss_send_len=%s bytes",
                          self.dpid, config_flags, miss_send_len)
        try:
            self.datapath.send_msg(parser.OFPSetConfig(
                                     self.datapath,
                                     config_flags,
                                     miss_send_len))
        except:
            #*** Log the error and return 0:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.logger.error("Failed to set switch config. "
                   "Exception %s, %s, %s",
                    exc_type, exc_value, exc_traceback)
            return 0
        return 1

    def packet_out(self, data, in_port, out_port, out_queue, no_queue=0):
        """
        Sends a supplied packet out switch port(s) in specific queue.

        Set no_queue=1 if want no queueing specified (i.e. for a flooded
        packet). Also use for Zodiac FX compatibility.

        Does not use Buffer IDs as they are unreliable resource.
        """
        ofproto = self.datapath.ofproto
        parser = self.datapath.ofproto_parser
        dpid = self.datapath.id
        #*** First build OF version specific list of actions:
        if no_queue:
            #*** Packet out with no queue:
            actions = [self.datapath.ofproto_parser.OFPActionOutput \
                             (out_port, 0)]

        else:
            #*** Note: out_port must come last!
            actions = [
                    parser.OFPActionSetQueue(out_queue),
                    parser.OFPActionOutput(out_port, 0)]

        #*** Now have we have actions, build the packet out message:
        out = parser.OFPPacketOut(
                    datapath=self.datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=in_port, actions=actions, data=data)

        self.logger.debug("Sending Packet-Out message dpid=%s port=%s",
                                    dpid, out_port)
        #*** Tell the switch to send the packet:
        self.datapath.send_msg(out)

    def set_switch_table_miss(self, miss_send_len):
        """
        Set a table miss rule on table 0 to send packets to
        the controller. This is required for OF versions higher
        than v1.0
        """
        ofproto = self.datapath.ofproto
        parser = self.datapath.ofproto_parser
        dpid = self.datapath.id
        self.logger.info("Setting table-miss flow entry on switch dpid=%s with"
                                       "miss_send_len=%s", dpid, miss_send_len)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                                                miss_send_len)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions)]
        mod = parser.OFPFlowMod(datapath=self.datapath, priority=0,
                                                match=match, instructions=inst)
        self.datapath.send_msg(mod)

class FlowTables(BaseClass):
    """
    This class provides an abstraction for the flow tables on
    an OpenFlow Switch
    """
    def __init__(self, config, datapath, offset):
        #*** Required for BaseClass:
        self.config = config
        #*** Set up Logging with inherited base class method:
        self.configure_logging(__name__, "switches_logging_level_s",
                                       "switches_logging_level_c")
        self.config = config
        self.datapath = datapath
        self.offset = offset
        self.dpid = datapath.id
        self.parser = datapath.ofproto_parser
        self.suppress_idle_timeout = config.get_value('suppress_idle_timeout')
        self.suppress_hard_timeout = config.get_value('suppress_hard_timeout')
        self.suppress_priority = config.get_value('suppress_priority')
        self.drop_idle_timeout = config.get_value('drop_idle_timeout')
        self.drop_hard_timeout = config.get_value('drop_hard_timeout')
        self.drop_priority = config.get_value('drop_priority')
        #*** Unique value counters for Flow Mod cookies:
        self.flow_mod_cookie_forward = 1
        self.flow_mod_cookie_reverse = offset

    def suppress_flow(self, msg, in_port, out_port, out_queue):
        """
        Add flow entries to a switch to suppress further packet-in
        events while the flow is active.

        Prefer to do fine-grained match where possible.
        Install reverse matches as well for TCP flows.

        Do not install suppression for these types of flow:
        - DNS (want to harvest identity)
        - ARP (want to harvest identity)
        - DHCP (want to harvest identity)
        - LLDP (want to harvest identity)
        """
        #*** Extract parameters:
        pkt = packet.Packet(msg.data)
        pkt_ip4 = pkt.get_protocol(ipv4.ipv4)
        pkt_ip6 = pkt.get_protocol(ipv6.ipv6)
        pkt_tcp = pkt.get_protocol(tcp.tcp)
        pkt_udp = pkt.get_protocol(udp.udp)
        idle_timeout = self.suppress_idle_timeout
        hard_timeout = self.suppress_hard_timeout
        priority = self.suppress_priority
        #*** Dict for results:
        result = {'match_type': 'ignore', 'forward_cookie': 0,
                 'forward_match': '', 'reverse_cookie': 0, 'reverse_match': '',
                 'client_ip': ''}
        self.logger.debug("event=add_flow out_queue=%s", out_queue)
        #*** Install flow entry(ies) based on type of flow:
        if pkt_tcp:
            #*** Do not suppress TCP DNS:
            if pkt_tcp.src_port == 53 or pkt_tcp.dst_port == 53:
                return result
            #*** Install two flow entries for TCP so that return traffic
            #*** is also suppressed:
            if pkt_ip4:
                forward_match = self.match_ipv4_tcp(pkt_ip4.src, pkt_ip4.dst,
                                            pkt_tcp.src_port, pkt_tcp.dst_port)
                reverse_match = self.match_ipv4_tcp(pkt_ip4.dst, pkt_ip4.src,
                                            pkt_tcp.dst_port, pkt_tcp.src_port)
            elif pkt_ip6:
                forward_match = self.match_ipv6_tcp(pkt_ip6.src, pkt_ip6.dst,
                                            pkt_tcp.src_port, pkt_tcp.dst_port)
                reverse_match = self.match_ipv6_tcp(pkt_ip6.dst, pkt_ip6.src,
                                            pkt_tcp.dst_port, pkt_tcp.src_port)
            else:
                #*** Unknown protocol so warn and exit:
                self.logger.warning("Unknown protocol, not installing flow "
                                    "suppression entries")
                return result
            #*** Actions:
            forward_actions = self.actions(out_port, out_queue)
            reverse_actions = self.actions(in_port, out_queue)
            #*** Cookies:
            forward_cookie = self.flow_mod_cookie_forward
            reverse_cookie = self.flow_mod_cookie_reverse
            #*** Now have matches and actions. Install to switch:
            self.add_flow(forward_match, forward_actions,
                                 priority=priority,
                                 idle_timeout=idle_timeout,
                                 hard_timeout=hard_timeout,
                                 cookie=forward_cookie)
            self.add_flow(reverse_match, reverse_actions,
                                 priority=priority,
                                 idle_timeout=idle_timeout,
                                 hard_timeout=hard_timeout,
                                 cookie=reverse_cookie)
            if pkt_ip4:
                #*** Convert IPv4 addrs back to dotted decimal for storing:
                forward_match['ipv4_src'] = pkt_ip4.src
                forward_match['ipv4_dst'] = pkt_ip4.dst
                reverse_match['ipv4_src'] = pkt_ip4.dst
                reverse_match['ipv4_dst'] = pkt_ip4.src
            result['match_type'] = 'dual'
            result['forward_cookie'] = forward_cookie
            result['forward_match'] = forward_match
            result['reverse_cookie'] = reverse_cookie
            result['reverse_match'] = reverse_match
            result['client_ip'] = pkt_ip4.src
            #*** Increment flow mod cookies ready for next use:
            if self.flow_mod_cookie_forward < self.offset:
                self.flow_mod_cookie_forward += 1
            else:
                self.logger.info("flow_mod_cookie_forward rolled")
                self.flow_mod_cookie_forward = 1
            self.flow_mod_cookie_reverse += 1
            return result
        else:
            if pkt_udp:
                #*** Do not suppress UDP DNS OR DHCP:
                if (pkt_udp.src_port == 53 or pkt_udp.dst_port == 53 or
                             pkt_udp.src_port == 67 or pkt_udp.dst_port == 67):
                    return result
            if pkt_ip4:
                #*** Match IPv4 packet
                match = self.match_ipv4(pkt_ip4.src, pkt_ip4.dst,
                                                                 pkt_ip4.proto)
            elif pkt_ip6:
                #*** Match IPv6 packet
                match = self.match_ipv6(pkt_ip6.src, pkt_ip6.dst)
            else:
                #*** Non-IP packet, ignore:
                return result
            #*** Actions:
            actions = self.actions(out_port, out_queue)
            #*** Cookie:
            cookie = self.flow_mod_cookie_forward
            #*** Now have matches and actions. Install to switch:
            self.add_flow(match, actions,
                                 priority=priority,
                                 idle_timeout=idle_timeout,
                                 hard_timeout=hard_timeout,
                                 cookie=cookie)
            if pkt_ip4:
                #*** Convert IPv4 addrs back to dotted decimal for storing:
                match['ipv4_src'] = pkt_ip4.src
                match['ipv4_dst'] = pkt_ip4.dst
            result['match_type'] = 'single'
            result['forward_cookie'] = cookie
            result['forward_match'] = match
            result['client_ip'] = pkt_ip4.src
            #*** Increment flow mod cookie ready for next use:
            self.flow_mod_cookie_forward += 1
            return result

    def drop_flow(self, msg):
        """
        Add flow entry to a switch to suppress further packet-in
        events for a particular flow.

        Prefer to do fine-grained match where possible.

        TCP or UDP source ports are not matched as ephemeral
        """
        #*** Extract parameters:
        pkt = packet.Packet(msg.data)
        pkt_ip4 = pkt.get_protocol(ipv4.ipv4)
        pkt_ip6 = pkt.get_protocol(ipv6.ipv6)
        pkt_tcp = pkt.get_protocol(tcp.tcp)
        pkt_udp = pkt.get_protocol(udp.udp)
        idle_timeout = self.drop_idle_timeout
        hard_timeout = self.drop_hard_timeout
        priority = self.drop_priority
        #*** Dict for results:
        result = {'match_type': 'ignore', 'forward_cookie': 0,
                 'forward_match': '', 'reverse_cookie': 0, 'reverse_match': '',
                 'client_ip': ''}
        self.logger.debug("event=drop_flow")
        #*** Drop action is the implicit in setting no actions:
        drop_action = 0
        #*** Install flow entry based on type of flow:
        if pkt_tcp:
            if pkt_ip4:
                drop_match = self.match_ipv4_tcp(pkt_ip4.src, pkt_ip4.dst,
                                            0, pkt_tcp.dst_port)
            elif pkt_ip6:
                drop_match = self.match_ipv6_tcp(pkt_ip6.src, pkt_ip6.dst,
                                            0, pkt_tcp.dst_port)
            else:
                #*** Unknown protocol so warn and exit:
                self.logger.warning("Unknown IP protocol, not installing flow "
                                    "drop entry for TCP")
                return result
        elif pkt_udp:
            if pkt_ip4:
                drop_match = self.match_ipv4_udp(pkt_ip4.src, pkt_ip4.dst,
                                            0, pkt_udp.dst_port)
            elif pkt_ip6:
                drop_match = self.match_ipv6_udp(pkt_ip6.src, pkt_ip6.dst,
                                            0, pkt_udp.dst_port)
            else:
                #*** Unknown protocol so warn and exit:
                self.logger.warning("Unknown IP protocol, not installing flow "
                                    "drop entry for UDP")
                return result
        elif pkt_ip4:
            #*** Match IPv4 packet
            drop_match = self.match_ipv4(pkt_ip4.src, pkt_ip4.dst,
                                                                 pkt_ip4.proto)
        elif pkt_ip6:
            #*** Match IPv6 packet
            drop_match = self.match_ipv6(pkt_ip6.src, pkt_ip6.dst)
        else:
            #*** Non-IP packet, ignore:
            self.logger.warning("Drop not installed as non-IP")
            return 0
        #*** Cookie:
        cookie = self.flow_mod_cookie_forward
        #*** Now have match and action. Install to switch:
        self.logger.debug("Installing drop rule to dpid=%s", self.dpid)
        self.add_flow(drop_match, drop_action, priority=priority,
                          idle_timeout=idle_timeout, hard_timeout=hard_timeout,
                          cookie=cookie)
        result['match_type'] = 'single'
        result['forward_cookie'] = cookie
        if pkt_ip4:
            #*** Convert IPv4 addrs back to dotted decimal for storing:
            drop_match['ipv4_src'] = pkt_ip4.src
            drop_match['ipv4_dst'] = pkt_ip4.dst
            result['client_ip'] = pkt_ip4.src
        result['forward_match'] = drop_match
        #*** Increment flow mod cookie ready for next use:
        self.flow_mod_cookie_forward += 1
        return result

    def add_flow(self, match_d, actions, priority, idle_timeout, hard_timeout,
                    cookie):
        """
        Add a flow entry to a switch
        """
        #*** Convert match dict to an OFPMatch object:
        match = self.parser.OFPMatch(**match_d)
        ofproto = self.datapath.ofproto
        parser = self.datapath.ofproto_parser
        if actions:
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                                      actions)]
        else:
            inst = []
        mod = parser.OFPFlowMod(datapath=self.datapath,
                                cookie=cookie,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                priority=priority,
                                flags=ofproto.OFPFF_SEND_FLOW_REM,
                                match=match,
                                instructions=inst)
        self.logger.debug("Installing Flow Entry to dpid=%s match=%s",
                                    self.dpid, match)
        self.datapath.send_msg(mod)

    def actions(self, out_port, out_queue, no_queue=0):
        """
        Create actions for a switch flow entry. Specify the out port
        and QoS queue, and set no_queue=1 if don't want QoS set.
        Returns a list of action objects
        """
        if no_queue:
            #*** Set flow entry action without queueing specified:
            return [self.datapath.ofproto_parser.OFPActionOutput(out_port, 0)]
        else:
            return [self.datapath.ofproto_parser.OFPActionSetQueue(out_queue),
                    self.datapath.ofproto_parser.OFPActionOutput(out_port, 0)]

    def match_ipv4_tcp(self, ipv4_src, ipv4_dst, tcp_src, tcp_dst):
        """
        Match an IPv4 TCP flow on a switch.
        Passed IPv4 and TCP parameters and return
        an OpenFlow match object for this flow
        """
        if tcp_src:
            return dict(eth_type=0x0800,
                    ipv4_src=_ipv4_t2i(str(ipv4_src)),
                    ipv4_dst=_ipv4_t2i(str(ipv4_dst)),
                    ip_proto=6,
                    tcp_src=tcp_src,
                    tcp_dst=tcp_dst)
        else:
            return dict(eth_type=0x0800,
                    ipv4_src=_ipv4_t2i(str(ipv4_src)),
                    ipv4_dst=_ipv4_t2i(str(ipv4_dst)),
                    ip_proto=6,
                    tcp_dst=tcp_dst)

    def match_ipv4_udp(self, ipv4_src, ipv4_dst, udp_src, udp_dst):
        """
        Match an IPv4 UDP flow on a switch.
        Passed IPv4 and UDP parameters and return
        an OpenFlow match object for this flow
        """
        if udp_src:
            return dict(eth_type=0x0800,
                    ipv4_src=_ipv4_t2i(str(ipv4_src)),
                    ipv4_dst=_ipv4_t2i(str(ipv4_dst)),
                    ip_proto=17,
                    udp_src=udp_src,
                    udp_dst=udp_dst)
        else:
            return dict(eth_type=0x0800,
                    ipv4_src=_ipv4_t2i(str(ipv4_src)),
                    ipv4_dst=_ipv4_t2i(str(ipv4_dst)),
                    ip_proto=17,
                    udp_dst=udp_dst)

    def match_ipv6_tcp(self, ipv6_src, ipv6_dst, tcp_src, tcp_dst):
        """
        Match an IPv6 TCP flow on a switch.
        Passed IPv6 and TCP parameters and return
        an OpenFlow match object for this flow
        """
        if tcp_src:
            return dict(eth_type=0x86DD,
                    ipv6_src=ipv6_src,
                    ipv6_dst=ipv6_dst,
                    ip_proto=6,
                    tcp_src=tcp_src,
                    tcp_dst=tcp_dst)
        else:
            return dict(eth_type=0x86DD,
                    ipv6_src=ipv6_src,
                    ipv6_dst=ipv6_dst,
                    ip_proto=6,
                    tcp_dst=tcp_dst)

    def match_ipv6_udp(self, ipv6_src, ipv6_dst, udp_src, udp_dst):
        """
        Match an IPv6 UDP flow on a switch.
        Passed IPv6 and UDP parameters and return
        an OpenFlow match object for this flow
        """
        if udp_src:
            return dict(eth_type=0x86DD,
                    ipv6_src=ipv6_src,
                    ipv6_dst=ipv6_dst,
                    ip_proto=17,
                    udp_src=udp_src,
                    udp_dst=udp_dst)
        else:
            return dict(eth_type=0x86DD,
                    ipv6_src=ipv6_src,
                    ipv6_dst=ipv6_dst,
                    ip_proto=17,
                    udp_dst=udp_dst)

    def match_ipv4(self, ipv4_src, ipv4_dst, ip_proto):
        """
        Match an IPv4 flow on a switch.
        Passed IPv4 parameters and return
        an OpenFlow match object for this flow
        """
        return dict(eth_type=0x0800,
                    ipv4_src=_ipv4_t2i(str(ipv4_src)),
                    ipv4_dst=_ipv4_t2i(str(ipv4_dst)),
                    ip_proto=ip_proto)

    def match_ipv6(self, ipv6_src, ipv6_dst):
        """
        Match an IPv6 flow on a switch.
        Passed IPv6 parameters and return
        an OpenFlow match object for this flow
        """
        return dict(eth_type=0x86DD,
                    ipv6_src=ipv6_src,
                    ipv6_dst=ipv6_dst)

#=============== Private functions:

def _ipv4_t2i(ip_text):
    """
    Turns an IPv4 address in text format into an integer.
    Borrowed from rest_router.py code
    """
    if ip_text == 0:
        return ip_text
    assert isinstance(ip_text, str)
    return struct.unpack('!I', addrconv.ipv4.text_to_bin(ip_text))[0]
