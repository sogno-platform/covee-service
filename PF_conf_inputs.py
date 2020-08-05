import numpy as np 
import time
import sys
import requests
import json
import csv

reqData = {
    "data": {
        "nodes": [5,6,7,8,9,10],
    }
}

headers = {'content-type': 'application/json'}
try:
    jsonData = (json.dumps(reqData)).encode("utf-8")
except:
    logging.warn("Malformed json")
result = requests.post("http://10.100.1.122:7070/set/nodes/data_nodes/", data=jsonData, headers=headers)