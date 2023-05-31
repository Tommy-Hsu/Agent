import sys
import socket
import selectors
import types
import argparse
import os
import yaml
import logging
import logging.config

'''
機器人團隊
(1) start_agv_follow 開始追隨, 
(2) end_agv_follow 停止追隨, 
(3) self_move 軌跡追蹤,   
(4) self_move_hold 軌跡追蹤的途中暫停,   
(5) self_move_resume 繼續進行軌跡追蹤
(6) agv_shut_down

語音團隊
(1) follow me
(2) go to nursing station

腦波團隊
(1) Idle
(2) move

量測團隊
(1) measurement_done

- 機器人忙錄中: robot_busy
   1 - 機器人啟動前往配膳間: robot_goto_kitchen
   2 - 等候服務人員放水瓶: caregiver_busy
   3 - 機器人正在過來: robot_coming
   4 - 機器人正在回護理站: robot_goback_nursing_station
0 - 機器人待機: robot_idle

護理站充電樁 = 0 , 配膳間  = 311, 癱瘓病位A = 315
'''

parser = argparse.ArgumentParser()

class Agent():
    def __init__(self, h_ip, h_port, dst_ip, dst_port) -> None:
        self.ip = h_ip
        self.port = h_port
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.sel = selectors.DefaultSelector()
        self.location_list = ["0", "311", "315"] # 護理站 = 0, 配膳間 = 311, 癱瘓病位 = 315
        self.robot_location = "0"
        self.busy = 0

    def accept_wrapper(self, sock):
        conn, addr = sock.accept()  # Should be ready to read
        # print(f"Accepted connection from {addr}")
        logger.info(f"Accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.sel.register(conn, events, data=data)

    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)  # Should be ready to read
            message = recv_data.decode()
            if recv_data:
                # print(f"Receive '{message}' from {data.addr}")
                logger.info(f"Receive '{message}' from {data.addr}")

                # 腦波團隊 護理站去配膳間
                if message == "give_me_water" and not(self.busy):
                    self.forward_command("self_move_OW")
                    data.outb += b"OK"
                    self.busy = 1
                
                # 語音團隊 配膳間去病房
                elif message == "put_water_into_robot" and not(self.busy):
                    self.forward_command("self_move_WA")
                    data.outb += b"OK"
                    self.busy = 3
                
                elif message == "robot_go_back" and not(self.busy):
                    self.forward_command("self_move_AO")
                    data.outb += b"OK"
                    self.busy = 4

                # 讓機器人說話
                # elif message == "water":
                #     data.outb += b"OK"
                #     self.forward_command("userA_want_water")

                # 機器人團隊
                elif message == "agv_shut_down":
                    data.outb += b"OK"
                    self.forward_command("debug")

                # 更新機器人位置(debug用) && 解除機器人忙碌狀態
                # elif message in self.location_list:
                #     self.robot_location = message
                #     if self.robot_location in self.location_list:
                #         self.busy = 0
                #     data.outb += b"OK"

                # 解除機器人狀態
                elif message == "rbf":
                    data.outb += b"OK"
                    self.busy = 0

                else:
                    if self.busy == 1:
                        data.outb += b"robot_goto_kitchen"
                    # elif self.busy == 2:
                    #     data.outb += b"caregiver_busy"
                    elif self.busy == 3:
                        data.outb += b"robot_coming"
                    elif self.busy == 4:
                        data.outb += b"robot_goback_nursing_station"
                    else:
                        data.outb += b"Wrong Command"
                
            else:
                # print(f"Closing connection to {data.addr}")
                logger.info(f"Closing connection to {data.addr}\n")
                self.sel.unregister(sock)
                sock.close()
                print('Busy\n' if(self.busy) else 'Free\n')

        if mask & selectors.EVENT_WRITE:
            if data.outb:
                # print(f"Send {data.outb!r} to {data.addr}")
                logger.warning(f"Send {data.outb!r} to {data.addr}") if (b"Wrong Command" in data.outb) else logger.info(f"Send {data.outb!r} to {data.addr}")
                sent = sock.send(data.outb)  # Should be ready to write
                data.outb = data.outb[sent:]

    def forward_command(self, command):
        dst_addr = (self.dst_ip, self.dst_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(dst_addr)
            # print(f"Connect to {dst_addr}")
            logger.info(f"Connect to {dst_addr}")

            s.sendall(command.encode())
            # print(f"Send command: {command}")
            logger.info(f"Send command: {command}")

            # blocking
            data = s.recv(1024)
            # non-blocking
            # s.settimeout(3)
            # try:
            #     data = s.recv(1024)
            #     logger.info(f"Receive: {data.decode()}")
            # except:
            #     print("Timeout")

            # print(f"Receive: {data.decode()}")
            logger.info(f"Receive: {data.decode()}")

    def run(self):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((self.ip, self.port))
        lsock.listen()
        print(f"Listening on {(self.ip, self.port)}")
        print('Busy\n' if(self.busy) else 'Free\n')
        logger.info(f"Listening on {(self.ip, self.port)}\n")
        lsock.setblocking(False)
        self.sel.register(lsock, selectors.EVENT_READ, data=None)

        try:
            while True:
                events = self.sel.select(timeout=None)
                for key, mask in events:
                    if key.data is None:
                        self.accept_wrapper(key.fileobj)
                    else:
                        self.service_connection(key, mask)
        except KeyboardInterrupt:
            print("Caught keyboard interrupt, exiting")
        finally:
            self.sel.close()

if __name__ == '__main__':

    with open('./config.yaml', 'r') as stream:
        if not(os.path.isdir('./logs')): os.makedirs('./logs')
        config = yaml.load(stream, Loader=yaml.FullLoader)
    logging.config.dictConfig(config)
    logger = logging.getLogger('my_module2')

    parser.add_argument("--h_ip", help="The host server IP address", required=True)
    parser.add_argument("--h_port", help="The host server port number", type=int, required=True)
    parser.add_argument("--dst_ip", help="The destination server IP address", required=True)
    parser.add_argument("--dst_port", help="The destination server port number", type=int, required=True)
    args = parser.parse_args()
    
    agent = Agent(args.h_ip, args.h_port, args.dst_ip, args.dst_port)
    agent.run()