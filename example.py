#!/usr/bin/env python

import random
import subprocess

while True:
    req = input().strip().split("\t")
    if req[0] == "?":
        print("gpu_fan_speed\tfrandom")
    elif req[0] == "gpu_fan_speed":
        if (req[1] == "value"):
            stdout = subprocess.run(["nvidia-smi", "-q"], check=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
            for string in stdout.split("\n"):
                if "Fan Speed" in string:
                    print(string.split(":")[1].replace("%", "").replace(" ", ""))
                    break
            else:
                print()
        elif (req[1] == "min"):
            print(0)
        elif (req[1] == "max"):
            print(100)
        elif (req[1] == "unit"):
            print("%")
        else:
            print()
    elif req[0] == "frandom":
        if (req[1] == "value"):
            print(random.random())
        else:
            print()
    else:
        print()
