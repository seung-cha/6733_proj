import zmq # TODO install pyzmq
import numpy as np
import multiprocessing
import time
import re
import tables as tb

from scripts import WriterProcess



# TODO: ANOTHER PORT FOR TX/RX
# --- Configuration ---
GNB_IP_ADDRESS = "127.0.0.1"  # Or the IP address of the machine running the gNB
DATA_PORT = 55555
CONTROL_PORT = 55556

WRITER_PORT = 55558



# TODO: another process for TX/RX
def iq_subscriber_process(data_endpoint, stop_event, writer_endpoint):
    """
    This function runs in a separate process and continuously subscribes to the
    IQ data stream from the gNodeB.
    """

    print(f"[Sub-Process] Connecting to data publisher at {data_endpoint}...")
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Use a poller to avoid blocking indefinitely on recv
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    
    socket.connect(data_endpoint)
    socket.setsockopt_string(zmq.SUBSCRIBE, "tx_stream")
    socket.setsockopt_string(zmq.SUBSCRIBE, "rx_stream")
    print("[Sub-Process] Subscribed to 'tx_stream' and 'rx_stream' topics.")

    writer_socket = context.socket(zmq.PUB)
    writer_socket.connect(writer_endpoint)

    while not stop_event.is_set():
        # Poll for incoming messages with a timeout to allow checking the stop_event
        socks = dict(poller.poll(timeout=500))
        if socket in socks and socks[socket] == zmq.POLLIN:
            msg = socket.recv_multipart()
            writer_socket.send_multipart(msg)

            

    
    print("[Sub-Process] Subscriber process stopping...")
    socket.close()
    context.term()
    print("[Sub-Process] Subscriber process stopped.")

def send_control_command(control_endpoint, command):
    """
    Sends a command to the gNodeB's control socket and waits for a reply.
    """
    # Each command gets its own short-lived context and socket
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.LINGER, 0) # Discard pending messages on close
    socket.connect(control_endpoint)

    try:
        print(f"[Controller] Sending command: '{command}' to {control_endpoint}")
        socket.send_string(command)
        
        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)
        
        if poller.poll(3000):  # 3-second timeout for reply
            reply = socket.recv_string()
            print(f"[Controller] Received reply: {reply}")
        else:
            print("[Controller] ERROR: No reply received from gNodeB. Is it running?")

    except zmq.ZMQError as e:
        print(f"[Controller] ZeroMQ Error: {e}")
    finally:
        socket.close()
        context.term()

# TODO: Command for monostatic sample acquisition
def print_menu():
    """Prints the user menu."""
    print("\n" + "="*40)
    print("        OAI IQ Stream Controller")
    print("="*40)
    print("  --- TX Commands ---")
    print("  ctx         : Stream TX continuously (-1)")
    print("  stx         : Stop streaming TX (0)")
    print("  <num>tx     : Stream <num> TX packets (e.g. 100tx)")
    print("\n  --- RX Commands ---")
    print("  crx         : Stream RX continuously (-1)")
    print("  srx         : Stop streaming RX (0)")
    print("  <num>rx     : Stream <num> RX packets (e.g. 100rx)")
    print("\n  --- General ---")
    print("  q           : Quit")
    print("="*40)

if __name__ == "__main__":
    # Ensure the multiprocessing context is correctly handled on all platforms
    multiprocessing.freeze_support()

    data_endpoint = f"tcp://{GNB_IP_ADDRESS}:{DATA_PORT}"
    control_endpoint = f"tcp://{GNB_IP_ADDRESS}:{CONTROL_PORT}"
    writer_endpoint = f'tcp://localhost:{WRITER_PORT}'

    # Create a multiprocessing Event to signal the subscriber process to stop
    stop_event = multiprocessing.Event()
    
    # Create the subscriber process
    subscriber = multiprocessing.Process(target=iq_subscriber_process, args=(data_endpoint, stop_event, writer_endpoint))
    subscriber.daemon = True
    subscriber.start()

    #Create a writer process
    writer = multiprocessing.Process(target= WriterProcess, args=(writer_endpoint,))
    writer.daemon = True
    writer.start()

    # Create socket
    writer_context = zmq.Context()
    writer_socket = writer_context.socket(zmq.PUB)
    writer_socket.connect(writer_endpoint)


    time.sleep(1)  # Give the subscriber a moment to start up

    print_menu()

    try:
        while True:
            user_input = input("Enter command > ").strip().lower()

            if user_input == 'q':
                print("Quitting...")
                break
            elif user_input == 'ctx':
                send_control_command(control_endpoint, "set_tx -1")
            elif user_input == 'stx':
                send_control_command(control_endpoint, "set_tx 0")
            elif user_input == 'crx':
                send_control_command(control_endpoint, "set_rx -1")
            elif user_input == 'srx':
                send_control_command(control_endpoint, "set_rx 0")
            else:
                match_tx = re.match(r"(\d+)tx", user_input)
                match_rx = re.match(r"(\d+)rx", user_input)

                if match_tx:
                    count = match_tx.group(1)

                    # Create file
                    writer_socket.send('new'.encode('utf-8'))
                    send_control_command(control_endpoint, f"set_tx {count}")
                elif match_rx:
                    count = match_rx.group(1)
                    # Create file
                    writer_socket.send('new'.encode('utf-8'))
                    send_control_command(control_endpoint, f"set_rx {count}")
                else:
                    print("Invalid command. Please use the format shown in the menu.")
            
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down.")
    finally:
        # Stop the writer server
        writer_socket.send('stop'.encode('utf-8'))
        if writer.is_alive():
            print('Waiting for writer to stop')
            writer.join(timeout= 2.0)
        
        if writer.is_alive():
            print('Terminating writer')
            writer.terminate()
            writer.join()
        

        print("Main process: Notifying subscriber to stop...")
        stop_event.set()
        if subscriber.is_alive():
            subscriber.join(timeout=2.0) # Wait for the process to finish
        if subscriber.is_alive():
            print("Main process: Subscriber did not exit cleanly, terminating...")
            subscriber.terminate() # Forcefully terminate if it doesn't stop
            subscriber.join()
            
        print("Main process finished.")
