import IPC

CHAT_QUERY_MSG = "chatQuery"
CHAT_QUERY_MSG_FMT = "string"
CHAT_RESPONSE_MSG = "chatResponse"
CHAT_RESPONSE_MSG_FMT = "string"


def chatQueryHandler(msgRef, callData, clientData):
    print("chatQueryHandler received:", callData)
    response = callData
    IPC.IPC_respondData(msgRef, CHAT_RESPONSE_MSG, "Handling: " + response)

if __name__ == "__main__":
    done = False

    print("Starting chatGPT responder...")

    IPC.IPC_connect("chatResponder")
    IPC.IPC_defineMsg(CHAT_QUERY_MSG, IPC.IPC_VARIABLE_LENGTH,
                      CHAT_QUERY_MSG_FMT)
    IPC.IPC_subscribeData(CHAT_QUERY_MSG, chatQueryHandler, None)
    IPC.IPC_defineMsg(CHAT_RESPONSE_MSG, IPC.IPC_VARIABLE_LENGTH,
                      CHAT_RESPONSE_MSG_FMT)
    while (not done): 
        IPC.IPC_listen(250)
    IPC.IPC_disconnect()
