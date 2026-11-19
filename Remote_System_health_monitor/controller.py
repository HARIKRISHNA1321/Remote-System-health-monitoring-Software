from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER,set_ev_cls
from os_ken.lib.packet import packet,ethernet,ether_types
from os_ken.ofproto import ofproto_v1_3

class BasicController(app_manager.OSKenApp):

    OFP_VERSIONS=[ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(BasicController,self).__init__(*args,**kwargs)
        self.mac_to_port={}

    def add_flow(self,dp,priority,match,actions,idle_timeout=0):
        ofp=dp.ofproto
        parser=dp.ofproto_parser

        instructions=[
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod=parser.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout
        )

        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def switch_features_handler(self,ev):
        dp=ev.msg.datapath
        ofp=dp.ofproto
        parser=dp.ofproto_parser

        self.mac_to_port[dp.id]={}

        delete=parser.OFPFlowMod(
            datapath=dp,
            command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()
        )
        dp.send_msg(delete)

        normal_match=parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst='10.0.0.4',
            ip_proto=17,
            udp_dst=5005
        )

        normal_actions=[
            parser.OFPActionSetQueue(0),
            parser.OFPActionOutput(4)
        ]

        self.add_flow(dp,200,normal_match,normal_actions)

        critical_match=parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst='10.0.0.4',
            ip_proto=17,
            udp_dst=5006
        )

        critical_actions=[
            parser.OFPActionSetQueue(1),
            parser.OFPActionOutput(4)
        ]

        self.add_flow(dp,200,critical_match,critical_actions)

        normal_test_match=parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst='10.0.0.4',
            ip_proto=17,
            udp_dst=5201
        )

        normal_test_actions=[
            parser.OFPActionSetQueue(0),
            parser.OFPActionOutput(4)
        ]

        self.add_flow(
            dp,210,normal_test_match,normal_test_actions
        )

        critical_test_match=parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst='10.0.0.4',
            ip_proto=17,
            udp_dst=5202
        )

        critical_test_actions=[
            parser.OFPActionSetQueue(1),
            parser.OFPActionOutput(4)
        ]

        self.add_flow(
            dp,210,critical_test_match,critical_test_actions
        )

        self.logger.info("UDP 5201 -> Queue 0 -> Port 4")
        self.logger.info("UDP 5202 -> Queue 1 -> Port 4")

        actions=[
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(
            dp,
            0,
            parser.OFPMatch(),
            actions
        )

        self.logger.info("Switch connected: %s",dp.id)
        self.logger.info("UDP 5005 -> Queue 0 -> Port 4")
        self.logger.info("UDP 5006 -> Queue 1 -> Port 4")

    @set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
    def packet_in_handler(self,ev):
        msg=ev.msg
        dp=msg.datapath
        ofp=dp.ofproto
        parser=dp.ofproto_parser

        pkt=packet.Packet(msg.data)
        eth=pkt.get_protocol(ethernet.ethernet)

        if eth is None or eth.ethertype==ether_types.ETH_TYPE_LLDP:
            return

        dpid=dp.id
        in_port=msg.match['in_port']

        self.mac_to_port.setdefault(dpid,{})
        self.mac_to_port[dpid][eth.src]=in_port

        out_port=self.mac_to_port[dpid].get(
            eth.dst,
            ofp.OFPP_FLOOD
        )

        actions=[
            parser.OFPActionOutput(out_port)
        ]

        if out_port!=ofp.OFPP_FLOOD:
            match=parser.OFPMatch(
                in_port=in_port,
                eth_dst=eth.dst
            )

            self.add_flow(
                dp,
                10,
                match,
                actions,
                idle_timeout=60
            )

        data=None

        if msg.buffer_id==ofp.OFP_NO_BUFFER:
            data=msg.data

        out=parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )

        dp.send_msg(out)
