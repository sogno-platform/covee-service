from pypower.api import *
from pypower.ext2int import ext2int
from pypower.idx_brch import F_BUS, T_BUS, TAP, BR_R, BR_X, BR_B, RATE_A, PF, QF, PT, QT
from pypower.idx_bus import BUS_TYPE, REF, PD, QD, VM, VA, VMAX, VMIN
from pypower.idx_gen import GEN_BUS, PG, QG, PMAX, PMIN, QMAX, QMIN, VG
from pypower.int2ext import int2ext

from cases.case_10_nodes import case_10_nodes
from csv_files.read_profiles import read_profiles

import numpy as np
from pypower.ppoption import ppoption
import csv
import os
import coloredlogs, logging, threading
from threading import Thread
from submodules.dmu.dmu import dmu
from submodules.dmu.httpSrv import httpSrv
import time
import sys
import requests
import json
import csv
import argparse


parser = argparse.ArgumentParser()
parser.add_argument('--ext_port', nargs='*', required=True)
args = vars(parser.parse_args())
ext_port = args['ext_port'][0]


coloredlogs.install(level='DEBUG',
fmt='%(asctime)s %(levelname)-8s %(name)s[%(process)d] %(message)s',
field_styles=dict(
    asctime=dict(color='green'),
    hostname=dict(color='magenta'),
    levelname=dict(color='white', bold=True),
    programname=dict(color='cyan'),
    name=dict(color='blue')))
logging.info("Program Start")


def initialize( name, profiles):
    # Input Data
    # =============================================================
    ppc = name
    pvproduction = profiles[0]
    demandprofile_P = profiles[1]

def run_Power_Flow(ppc, active_nodes, active_power,reactive_power,pv_profile):
    ppc = ext2int(ppc)      # convert to continuous indexing starting from 0
    BUS_TYPE = 1

    # Gather information about the system
    # =============================================================
    baseMVA, bus, gen, branch, cost, VMAX, VMIN = \
        ppc["baseMVA"], ppc["bus"], ppc["gen"], ppc["branch"], ppc["gencost"], ppc["VMAX"], ppc["VMIN"]

    nb = bus.shape[0]                        # number of buses
    ng = gen.shape[0]                        # number of generators
    nbr = branch.shape[0]                    # number of branches

    for i in range(int(nb)):
        if bus[i][BUS_TYPE] == 3.0:
            pcc = i
        else:
            pass

    c = active_nodes
    for i in range(1,ng):
        if gen[i][0] in c:
            pass
        else:
            np.delete(ppc["gen"],(i),axis=0)       

    print("Number of Reactive Power Compensator = ",int(len(c)))
            
    # initialize vectors
    # =====================================================================
    q = [0.0] * int(len(c))
    p = []
    v_gen = []

    ############## SET THE ACTUAL LOAD AND GEN VALUES ###############-+
    for i in range(int(nb)-1):
        bus[i][PD] = 0.3 #- p_batt_array[i]
        bus[i][QD] = 0.0

    for i in range(int(len(c))):
        gen[i+1][QG] = reactive_power[i]
        gen[i+1][PG] = pv_profile[i] + active_power[i]

    ppc['bus'] = bus
    ppc['gen'] = gen
    ppc = int2ext(ppc)


    ############# RUN PF ########################
    opt = ppoption(VERBOSE=0, OUT_ALL=0, UT_SYS_SUM=0)
    results = runpf(ppc, opt)
    bus_results = results[0]['bus']

    for i in range(int(len(c))):
        v_gen.append(bus_results[int(c[i]-1)][VM])
        p.append(gen[i+1][PG])
    
    return v_gen,p,c


############################ Start the Server #######################################################

''' Initialize objects '''
dmuObj = dmu()

''' Start http server '''
httpSrvThread1 = threading.Thread(name='httpSrv',target=httpSrv, args=("0.0.0.0", 8000 ,dmuObj,))
httpSrvThread1.start()

httpSrvThread2 = threading.Thread(name='httpSrv',target=httpSrv, args=("0.0.0.0", int(ext_port) ,dmuObj,))
httpSrvThread2.start()
time.sleep(2.0)
#######################################################################################################


########################################################################################################
#########################  Section for Defining the Dictionaries  ######################################
########################################################################################################

dict_ext_cntr = {
    "data_cntr" : [],
    "data_nodes" : []
}

simDict = {
    "active_nodes" : [],
    "output_voltage": [],
    "active_power_control": [],
    "reactive_power_control": []
}

voltage_dict = {}
active_power_control_dict = {}
reactive_power_control_dict = {}
pv_input_dict = {}

# add the simulation dictionary to mmu object
dmuObj.addElm("simDict", simDict)
dmuObj.addElm("voltage_dict", voltage_dict)
dmuObj.addElm("active_power_control_dict", active_power_control_dict)
dmuObj.addElm("reactive_power_control_dict", reactive_power_control_dict)
dmuObj.addElm("pv_input_dict", pv_input_dict)

########################################################################################################
#########################  Section for Receiving Signal  ###############################################
########################################################################################################

def active_power_control_input(data,  *args):
    active_power_control_dict = {}  
    dmuObj.setDataSubset(data,"active_power_control_dict")
def reactive_power_control_input(data,  *args):
    reactive_power_control_dict = {}  
    dmuObj.setDataSubset(data,"reactive_power_control_dict")

def api_cntr_input(data,  *args):   
    tmpData = []
    logging.debug("RECEIVED EXTERNAL CONTROL")
    logging.debug(data)       
    dmuObj.setDataSubset(data,"simDict", "active_nodes")

# Receive from external Control
dmuObj.addElm("nodes", dict_ext_cntr)
dmuObj.addRx(api_cntr_input, "nodes", "data_nodes")

# Receive active power control
dmuObj.addElm("active_power", simDict)
dmuObj.addRx(active_power_control_input, "active_power", "active_power_control")
# Receive reactive power control
dmuObj.addElm("reactive_power", simDict)
dmuObj.addRx(reactive_power_control_input, "reactive_power", "reactive_power_control")

########################################################################################################
#########################  Section for Sending Signal  #################################################
########################################################################################################

def measurement_output(data, *args):

    reqData = {}
    reqData["data"] =  data
    # logging.debug("voltage sent")
    logging.debug(data)

    headers = {'content-type': 'application/json'}
    try:
        jsonData = (json.dumps(reqData)).encode("utf-8")
    except:
        logging.warn("Malformed json")
    try:
        for key in data.keys():
            if key == "voltage_measurements":
                result = requests.post("http://pv_centralized:8000/set/voltage/voltage_node/", data=jsonData, headers=headers)
            if key == "pv_input_measurements":
                result = requests.post("http://pv_centralized:8000/set/pv_input/pv_input_node/", data=jsonData, headers=headers)
    except:
        logging.warn("No connection to control")

dmuObj.addRx(measurement_output,"voltage_dict")
dmuObj.addRx(measurement_output,"pv_input_dict")




# read profiles from CSV files
# =======================================================================
profiles = read_profiles()
[PV_list, P_load_list] = profiles.read_csv()

ppc = case_10_nodes()
initialize(ppc, [PV_list, P_load_list])
k=0
try:
    while True:
        voltage_dict = {}
        active_nodes = dmuObj.getDataSubset("simDict","active_nodes")
        if not active_nodes:
            logging.debug("no input received")
            active_nodes = list(np.array(np.matrix(ppc["gen"])[:,0]).flatten())
            active_nodes = active_nodes[1:len(active_nodes)]
        else:
            active_nodes = list(active_nodes.values())[0]
        logging.debug("active nodes")
        logging.debug(active_nodes)

        active_power_value = dmuObj.getDataSubset("active_power_control_dict")
        active_power = active_power_value.get("active_power", None)
        reactive_power_value = dmuObj.getDataSubset("reactive_power_control_dict")
        reactive_power = reactive_power_value.get("reactive_power", None)
        if not active_power or len(active_nodes)!=len(list(active_power.values())):
            p_value = [0.0] * len(active_nodes)
        else:
            p_value = list(active_power.values())
        if not reactive_power or len(active_nodes)!=len(list(reactive_power.values())):
            q_value = [0.0] * len(active_nodes)
        else:
            q_value = list(reactive_power.values())

        [v_gen,p,c] = run_Power_Flow(ppc,active_nodes,p_value,q_value,PV_list[k][:])
        # logging.debug("v_gen, p, c")
        # logging.debug([v_gen,p,c])
      
        for i in range(len(c)):
            voltage_dict["node_"+str(active_nodes[i])] = v_gen[i]
            pv_input_dict["node_"+str(active_nodes[i])] = PV_list[k][i]
        dmuObj.setDataSubset({"voltage_measurements": voltage_dict},"voltage_dict")
        dmuObj.setDataSubset({"pv_input_measurements": pv_input_dict},"pv_input_dict")

        time.sleep(1.0)
        k = min(k+1,300)
        print(k)

except (KeyboardInterrupt, SystemExit):
    print('simulation finished')