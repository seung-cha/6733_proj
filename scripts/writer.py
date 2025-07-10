import tables as tb
from datetime import datetime
from typing import Literal
import zmq
import numpy as np


class Entry(tb.IsDescription):
    """
    Record of each table (rx, tx)
    """
    timestamp = tb.UInt64Col(pos= 0)
    count = tb.Int32Col(pos= 1)
    real = tb.Int16Col(pos= 2)
    im = tb.Int16Col(pos= 3)

class Record:
    """
    Representation of m5 file with two tables (rx, tx).
    """
    def __init__(self, name= None):
        
        if name is None:
            name = f'{datetime.now().strftime('%H;%M;%S;%d-%m-%y')}.h5'
        else:
            name = f'{name}.h5'

        self.file = tb.open_file(name, mode= 'w')
        self.rx_group = self.file.create_group(self.file.root, 'rx_group')
        self.tx_group = self.file.create_group(self.file.root, 'tx_group')
        self.rx_tables: list[tb.Table] = []
        self.tx_tables: list[tb.Table] = []

    def __del__(self):
        if self.file is None:
            return
        
        for t in self.rx_tables:
            t.flush()

        for t in self.tx_tables:
            t.flush()
        
        self.file.close()

    def Record(self, samples, num_antennas, num_samples, timestamp, group: Literal['rx', 'tx']= None):
        if self.file is None:
            print('Record() failed to record data: File not open')
            return
        
        if group is None:
            print('Record() failed: group is not specified.')
            return
        
        if group == 'rx':
            self._MakeRxTable(num_antennas)
        else:
            self._MakeTxTable(num_antennas)
        

        for i in range(num_antennas):
            for j in range(num_samples):
                if group == 'rx':
                    row = self.rx_tables[i].row
                else:
                    row = self.tx_tables[i].row
                
                row['timestamp'] = timestamp
                row['count'] = j
                row['real'] = samples[i][j][0]
                row['im'] = samples[i][j][1]
                row.append()

    def _MakeRxTable(self, num_antennas: int):
        """
        Assumes num_antennas will be fixed.
        """

        if self.file is None:
            print('MakeRxTable() was called without a file open!')
            exit(1)

        if len(self.rx_tables) > 0:
            if len(self.rx_tables) == num_antennas:
                return

            print('MakeRxTable() is called more than once. This is not allowed.')
            return
        
        for i in range(num_antennas):
            self.rx_tables.append(self.file.create_table(self.rx_group, f'antenna{i}', Entry))
    
    def _MakeTxTable(self, num_antennas: int):
        """
        Assumes num_antennas will be fixed.
        """

        if self.file is None:
            print('MakeTxTable() was called without a file open!')
            exit(1)

        if len(self.tx_tables) > 0:
            if len(self.tx_tables) == num_antennas:
                return

            print('MakeTxTable() is called more than once. This is not allowed.')
            return
        
        for i in range(num_antennas):
            self.tx_tables.append(self.file.create_table(self.tx_group, f'antenna{i}', Entry))
    



def get_samples(message, num_antennas, num_samples):
    """
    Return numpy array of dim [num_antennas][num_samples][2] {0: real, 1: imaginary }

    params:
        * message: raw message from recv_multipart()
    """

    # Get samples for each antenna
    # samples[num_antennas][num_samples][i], i = 0 (real), = 1 (imaginary)
    samples = np.zeros((num_antennas, num_samples, 2), dtype= np.int16)

    c16t = np.dtype(np.int16).newbyteorder('>') # big-endian int16
    for i in range(num_antennas):
        # First two msgs for topic and timestamp
        msg = np.frombuffer(message[2 + i], dtype= c16t)
        for j in range(num_samples):
            samples[i][j][0] = msg[j * 2]
            samples[i][j][1] = msg[j * 2 + 1]

    return samples



def WriterProcess(write_endpoint):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.bind(write_endpoint)
    socket.setsockopt_string(zmq.SUBSCRIBE, '')

    record = None

    rx_count = 0
    tx_count = 0

    print('Writer started')

    try:
        while True:
            multipart_msg = socket.recv_multipart()
            topic = multipart_msg[0].decode('utf-8')

            print('recev: ' + topic)
            if topic == ('new'): # Start a new recording session
                record = Record()
            elif topic == ('stop'):
                break
            else:
                timestamp = np.frombuffer(multipart_msg[1], dtype=np.uint64)[0]
                num_antennas = len(multipart_msg) - 2
                if num_antennas > 0:
                    num_samples = len(multipart_msg[2]) // 4  # Each sample is 4 bytes (complex<int16>)
                else:
                    num_samples = 0

                samples = get_samples(multipart_msg, num_antennas, num_samples)

                if topic == "rx_stream":
                    rx_count += 1
                    print(f"[DATA] RX Packet {rx_count:5d} | TS: {timestamp} | Ant: {num_antennas} | Samples/Ant: {num_samples}")
                    
                    if record is not None:
                        record.Record(samples, num_antennas, num_samples, timestamp, 'rx')
                elif topic == "tx_stream":
                    tx_count += 1
                    print(f"[DATA] TX Packet {tx_count:5d} | TS: {timestamp} | Ant: {num_antennas} | Samples/Ant: {num_samples}")
                    
                    if record is not None:
                        record.Record(samples, num_antennas, num_samples, timestamp, 'tx')

    except Exception:
        pass
    finally:
        del record
        print('writer ended')    
        

