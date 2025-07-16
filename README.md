1. Clone the repo
```bash
git clone https://github.com/seung-cha/6733_proj.git --recurse-submodules
```

# Ports used
* 55555: rx publisher
* 55556: tx publisher
* 55557: controller
* 55558: writer

# hdf5 file format
  - root
    - rx_group
      * antenna0
      * antenna1
      * ...
      * antennaN
    - tx_group
      * antenna0
      * antenna1
      * ...
      * antennaN

```
AntennaN [Table]

 |[timestamp]|[count]|[real]|[im] |
0| (ui32)    | (i32) |(i16) |(i16)|
1| ...       | ...   | ...  |     |
2| ...       | ...   | ...  |     |
```


# Simulate the Base Station

To build openairinterface, first install the necessary libraries
```
sudo apt-get install libzmq3-dev
sudo apt-get install libhdf5-dev
```


build openairinterface

```
cd openairinterface5g/cmake_targets
./build_oai -w SIMU --gNB -I
```
> -I installs packages. You can omit it in subsequent build calls.

Run the simulation
```
cd ../ # move to the root of openairinterface5g

# Start the simulation
sudo ./cmake_targets/ran_build/build/nr-softmodem  -O targets/PROJECTS/GENERIC-NR-5GC/CONF/gnb.sa.band78.fr1.106PRB.usrpb210.conf  --gNBs.[0].min_rxtxtime 6 --phy-test --rfsim
```

If all goes well, you should see the terminal output constantly updating:

```
[TXPATH] RU 0 tx_rf, writing to TS 114984960 with TS Offset 0, 187.3, unwrapped_frame 0, slot 3, flags 1, siglen+sf_extension 30720, returned 30720, E -inf
Reading 30720 RX samples at TS 114831360 for frame.slot 186.18 (0x7e1ae4285040) with TS Offset 0
[TXPATH] RU 0 tx_rf, writing to TS 115015680 with TS Offset 0, 187.4, unwrapped_frame 0, slot 4, flags 1, siglen+sf_extension 30720, returned 30720, E -inf
Reading 30720 RX samples at TS 114862080 for frame.slot 186.19 (0x7e1ae42a3040) with TS Offset 0
[TXPATH] RU 0 tx_rf, writing to TS 115046400 with TS Offset 0, 187.5, unwrapped_frame 0, slot 5, flags 1, siglen+sf_extension 30720, returned 30720, E -inf
...
```

Since this command is long, I suggest aliasing it in bashrc.
```
# In the root of our project folder
echo "export PROJ_6733=$(pwd)" >> ~/.bashrc
echo 'alias sim="sudo $PROJ_6733/openairinterface5g/cmake_targets/ran_build/build/nr-softmodem  -O $PROJ_6733/openairinterface5g/targets/PROJECTS/GENERIC-NR-5GC/CONF/gnb.sa.band78.fr1.106PRB.usrpb210.conf  --gNBs.[0].min_rxtxtime 6 --phy-test --rfsim"' >> ~/.bashrc
source ~/.bashrc
```

From now on, you can simply type `sim` to simulate the base station
```
sim
```

Once the project has finalised, remove the env variable and alias from bashrc:

```
xdg-open ~/.bashrc
# This opens up a text editor. 
# Go to the end of the file and remove the alias and env var.
```

# Run the Controller
we are given `iq_streamer_controller.py` to interactively receive `TX` and `RX` data from the base station. To run it, install the necessary packages:

> Recommended to set up a virtual environment beforehand.

```
pip install pyzmq
pip install tables
```

While the base station is running, run the python script:
```
python3 iq_streamer_controller.py
```

You will be greeted with a CLI:
```
========================================
        OAI IQ Stream Controller
========================================
  --- TX Commands ---
  ctx         : Stream TX continuously (-1)
  stx         : Stop streaming TX (0)
  <num>tx     : Stream <num> TX packets (e.g. 100tx)

  --- RX Commands ---
  crx         : Stream RX continuously (-1)
  srx         : Stop streaming RX (0)
  <num>rx     : Stream <num> RX packets (e.g. 100rx)

  --- General ---
  q           : Quit
========================================
```


Receive 100 samples of TX:
```
100tx
```

Outcome:
```
...
[DATA] TX Packet    97 | TS: 1346242560 | Ant: 1 | Samples/Ant: 30720
[DATA] TX Packet    98 | TS: 1346273280 | Ant: 1 | Samples/Ant: 30720
[DATA] TX Packet    99 | TS: 1346304000 | Ant: 1 | Samples/Ant: 30720
[DATA] TX Packet   100 | TS: 1346334720 | Ant: 1 | Samples/Ant: 30720
```

We can also alias the controller script:
```
echo 'alias run="python3 $PROJ_6733/iq_streamer_controller.py"' >> ~/.bashrc
source ~/.bashrc
```

> If you are using a virtual environment, prepend the command to activate it.

> For my case, it's ...="conda activate 6733_project; $PROJ_6733/..."

Hereafter, we can use `run` to run the controller:

```
run
```

# Modifications to Make
I've already marked files to be modified with TODO. (Please note that it's not as descriptive, since I myself also don't know exactly what to do).

These are the files that we need to modify:

```
openairinterface5g/executables/nr-ru-streamer.c
                           .../nr-ru.c
iq_streamer_controller.py
```

## Create Pipeline for RX and TX.

Right now, RX and TX data are transmitted using one port only, using two threads.

This makes it more difficult to reliably receive data, as parallelism does not guarantee that bytes are fully transmitted before transmitting another one.

We can address this issue by adding lock. However, this approach will be very inefficient.

Our goal is to create a separate pipeline that uses a different port, so that RX and TX data can be received in parallel without intereference.

This involves (roughly)
1. Creating two threads, one for RX, and the other for TX.
2. Creating communication pieplines, each using a different port
3. Receiving data separately from the conroller script

> Note the vague term 'communication pipeline'. I have no idea if we are using TCP or UDP yet.

## Decoding Packets

In `nr-ru-streamer.c`, There's a code to transmit RX and TX packet:

```cpp
    send_multipart_data("tx_stream", timestamp, tx_buffs, num_samples, num_antennas);

    send_multipart_data("rx_stream", timestamp, rx_buffs, num_samples, num_antennas);
```

At the moment, controller is disregarding `tx_buffs` and `rx_buffs`:

```python
print(f"[DATA] RX Packet {rx_count:5d} | TS: {timestamp} | Ant: {num_antennas} | Samples/Ant: {num_samples}")

print(f"[DATA] TX Packet {tx_count:5d} | TS: {timestamp} | Ant: {num_antennas} | Samples/Ant: {num_samples}")
```

Our job is to figure out the format for `tx_buffs` and `rx_buffs`, and decode them in the controller script.

## Storing Packets
Once the pipelines are set up and packet formats are realised & decoded, we can start storing data for our experiment. We store the data in `hdf5` format (recommended by Cheng). We already have installed the package for it (tables).

## TX/RX Correlation

The last step is to correlate `TX` and `RX` samples using correlate function in `numpy` or `scikit`. (Make sure we correlate the `TX` `RX` samples with the same timestamp)

# Collecting Sameples to Plot

1. Run the base station and `iq_streamer_controller.py`.
2. Type <num>all (e.g 10all) to collect <num> samples of TX and RX data
3. Run `Plot.ipynb`. Make sure to change the `FILE_NAME` defined in the file.
4. Observe the outcomes.