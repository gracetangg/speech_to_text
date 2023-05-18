import IPC
import sys

CHAT_QUERY_MSG = "chatQuery"

if __name__ == "__main__":

    print("Starting chatGPT tester...")

    IPC.IPC_connect("chatTester")

    for line in sys.stdin:
        line = line.rstrip()
        if line in ['q', 'quit']:
            break
        else:
            (response, status) = IPC.IPC_queryResponseData(CHAT_QUERY_MSG,
                                                           line, 10000)
            if (status == IPC.IPC_OK): 
                print("ChatGPT responded:", response)
            else: 
                print("Query timed out")
