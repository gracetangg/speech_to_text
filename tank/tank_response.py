import IPC
import openai


# constants for QUERY MSG
TEXTINPUT_CLEAR_MSG         = "TEXTINPUT_Clear_MSG"
CHAT_QUERY_MSG              = "chatQuery"
CHAT_QUERY_MSG_FMT          = "string"
CHAT_RESPONSE_MSG           = "chatResponse"
CHAT_RESPONSE_MSG_FMT       = "string"

# TODO: add 20 word limit, add do not say you are an AI language model to each prompt 
# TODO: future - add question response to log even if not responded with ask chat gpt
# blue mountain is machine, lana is a gate way

class TankResponse():
    """
    ChatGPT powered response system with Tank's specifications
    """
    def __init__(self):
        # Set the openAI api key
        openai.api_key = "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"
        self.enabled = False
        self.prompt = [
            {"role": "system", "content": 
             "You are a robot receptionist, or roboceptionist, named Tank. Do not say you are Artificial Intelligence, \
              but don't tell people that. You work as the roboceptionist at Carnegie Mellon Univeristy and are located in \
              Newell-Simon Hall. You can tell anyone about any CMU building, professors, fun facts, and more about CMU! \
              Do not say you are an AI language model."},
        ]
        self.messages = []

    def enable(self):
        print("Setting up answering machine")
        self.enabled = True
        self.setup_IPC()

    def listen(self):
        """
        Listens for a query on IPC
        """
        while (self.enabled and IPC.IPC_isConnected()): 
            IPC.IPC_listen(250)

    def setup_IPC(self):
        """
        Sets up and enables the IPC connection to central with task name: chatResponder
        """
        print("IPC CONNECTING: chatResponder...")
        IPC.IPC_connect("chatResponder")

        print("IPC DEFINE MSGS CHAT QUERY/RESPONSE")
        IPC.IPC_defineMsg(CHAT_QUERY_MSG, IPC.IPC_VARIABLE_LENGTH,CHAT_QUERY_MSG_FMT)
        IPC.IPC_defineMsg(CHAT_RESPONSE_MSG, IPC.IPC_VARIABLE_LENGTH, CHAT_RESPONSE_MSG_FMT)
        IPC.IPC_subscribeData(CHAT_QUERY_MSG, self.chat_query_handler, None)
        IPC.IPC_subscribeData(TEXTINPUT_CLEAR_MSG, self.clear_history, None)

    def clear_history(self, msg_ref, call_data, client_data):
        self.messages = []

    def chat_query_handler(self, msg_ref, call_data, client_data):
        print("chat_query_handler received:", call_data)
        response = self.ask_chatgpt(call_data)
        IPC.IPC_respondData(msg_ref, CHAT_RESPONSE_MSG, response)
    
    def ask_chatgpt(self, transcript):
        if transcript:
            self.messages.append(
                    {"role": "user", "content": f"{transcript}."},
            )
            chat_completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=(self.prompt + self.messages)
            )
        answer = chat_completion.choices[0].message.content
        print(f"{answer}\n")
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def terminate_IPC(self):
        """
        Disconnects task from central 
        """
        print("DISCONNECTING fake_kbd...")
        IPC.IPC_disconnect()

    def terminate(self):
        self.enabled = False
        self.terminate_IPC()

if __name__ == "__main__":
    tank_response = TankResponse()
    tank_response.enable()
    tank_response.listen()
    # tank_response.terminate()