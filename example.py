#!/usr/bin/env python
# SPDX-FileCopyrightText: 2023-2025 KerJoe <2002morozik@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import subprocess

while True:
    req = input().strip().split("\t")
    if req[0] == "?":
        print("gpu_fan_speed\tfrandom")
    elif req[0] == "gpu_fan_speed":
        if (req[1] == "value"):
            try:
                stdout = subprocess.run(["nvidia-smi", "-q"], check=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
                for string in stdout.split("\n"):
                    if "Fan Speed" in string:
                        print(string.split(":")[1].replace("%", "").replace(" ", ""))
                        break
                else:
                    print()
            except Exception:
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
