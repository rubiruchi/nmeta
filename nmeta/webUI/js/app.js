(function ($) {
    //-------- Models:
    var PacketIn = Backbone.Model.extend({
        defaults:{
            packetinImage:"img/packet_in.png",
            pi_rate: "pi rate default"
        },
        parse:function (response) {
            console.log(response);
            response.id = response._id;
            return response;
        }
    });

    //-------- Model of multiple PacketIn models:
    var PacketIns = Backbone.Collection.extend({
        model:PacketIn,
        url:'/v1/infrastructure/controllers/pi_rate',
    });

    //-------- Views:
    var PacketInView = Backbone.View.extend({
        tagName:"div",
        className:"packetinContainer",
        template:$("#packetinTemplate").html(),

        render:function () {
            var tmpl = _.template(this.template);

            this.$el.html(tmpl(this.model.toJSON()));
            return this;
        }
    });

    //-------- View of multiple PacketIns:
    var PacketInsView = Backbone.View.extend({
        el:$("#packetins"),

        initialize: function(){
          this.collection = new PacketIns();
            this.collection.fetch({
                error:function () {
                    console.log(arguments);
                }
            });
          this.render();

          this.collection.on("add", this.renderPacketIn, this);
        },

        render:function () {
            var that = this;
            _.each(this.collection.models, function (item) {
                that.renderPacketIn(item);
            });
        },

        renderPacketIn:function(item){
            var packetinView = new PacketInView({
                model: item
            });
            this.$el.append(packetinView.render().el);
        }
    });

    var packetinsView = new PacketInsView();

    //-------- Identities:
    //-------- Models:
    var Identity = Backbone.Model.extend({
        defaults:{
            participantImage:"img/participant.png",
            host_name: "not found",
            ip_address: "not found"
        },
    });

    //-------- Model of multiple Identity models:
    var Identities = Backbone.Collection.extend({
        model:Identity,
        url:'/v1/identities/current',
        parse:function (response) {
            console.log(response);
            response.id = response._id;
            //--- Parse response data from under _items key:
            return response._items;
        }
    });

    //-------- Views:
    var IdentityView = Backbone.View.extend({
        tagName:"tr",
        className:"identityContainer",
        template:$("#identityTemplate").html(),

        render:function () {
            var tmpl = _.template(this.template);

            this.$el.html(tmpl(this.model.toJSON()));
            return this;
        }
    });

    //-------- View of multiple Identities:
    var IdentitiesView = Backbone.View.extend({
        el:$("#identities"),

        initialize: function(){
          this.collection = new Identities();
            this.collection.fetch({
                error:function () {
                    console.log(arguments);
                }
            });
          this.render();

          this.collection.on("add", this.renderIdentity, this);
        },

        render:function () {
            var that = this;
            _.each(this.collection.models, function (item) {
                that.renderIdentity(item);
            });
        },

        renderIdentity:function(item){
            var identityView = new IdentityView({
                model: item
            });
            this.$el.append(identityView.render().el);
        }
    });

    var identitiesView = new IdentitiesView();

    //-------- Flows:
    //-------- Models:
    var Flow = Backbone.Model.extend({
        defaults:{
            flowImage:"img/flow.png"
        },
    });

    //-------- Model of multiple Flow models:
    var Flows = Backbone.Collection.extend({
        model:Flow,
        url:'/v1/flows/current',
        parse:function (response) {
            console.log(response);
            response.id = response._id;
            //--- Parse response data from under _items key:
            return response._items;
        }
    });

    //-------- Views:
    var FlowView = Backbone.View.extend({
        tagName:"tr",
        className:"flowContainer",
        template:$("#flowTemplate").html(),

        render:function () {
            var tmpl = _.template(this.template);

            this.$el.html(tmpl(this.model.toJSON()));
            return this;
        }
    });

    //-------- View of multiple Flows:
    var FlowsView = Backbone.View.extend({
        el:$("#flows"),

        initialize: function(){
          this.collection = new Flows();
            this.collection.fetch({
                error:function () {
                    console.log(arguments);
                }
            });
          this.render();

          this.collection.on("add", this.renderFlow, this);
        },

        render:function () {
            var that = this;
            _.each(this.collection.models, function (item) {
                that.renderFlow(item);
            });
        },

        renderFlow:function(item){
            var flowView = new FlowView({
                model: item
            });
            this.$el.append(flowView.render().el);
        }
    });

    var flowsView = new FlowsView();

})(jQuery);