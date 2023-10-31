import struct
import pvporcupine
import datetime

from threading import Thread
from threading import Event
import pyaudio
from six.moves import queue
import openai
import numpy as np
import whisper

import IPC
# import textinputInterface # comes from the cpp library hopefully...

# constants for KBD: 
TEXTINPUT_START_MSG         = "TEXTINPUT_Start_MSG"
TEXTINPUT_TEXT_MSG          = "TEXTINPUT_Text_MSG"
TEXTINPUT_KEYPRESS_MSG      = "TEXTINPUT_Keypress_MSG"
TEXTINPUT_CLEAR_MSG         = "TEXTINPUT_Clear_MSG"
TEXTINPUT_MESSAGE_FMT       = "string"

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
TIMEOUT = 15

porcupine = None
sound = None
audio_stream = None

access_key = "YmjdiYjeRf9LwFBJCFxf299XxeiDoMRITiAjyvHcvc/RlOI1JLCwZA==" 

# class KEYBOARD_MESSAGE(IPC.IPCdata):
#     _fields = ("player", "buffer")
#     def __init__(self, player, buffer):
#         self.player = player
#         self.buffer = buffer

class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk, audio_interface=None, audio_stream=None):
        self._rate = rate
        self._chunk = chunk
        self._audio_interface = audio_interface
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1, 
            rate=self._rate,
            input=True, 
            frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def enter(self):
        self.closed = False

    def __enter__(self): #entering the with
        self.closed = False
        return self
    
    def exit(self):
        self.closed = True
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self._buff.put(None)

    def __exit__(self, type, value, traceback): #exiting the with 
        self.closed = True
        self._buff.put(None)

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return in_data, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b''.join(data)

class QuitThread(Thread):
    def __init__(self, event, responses, stream):
        Thread.__init__(self)
        self.stopped = event
        self.responses = responses
        self.exc = None
        self.quit_time = False
        self.stream = stream

    def clone(self):
        return QuitThread(self.stopped, self.responses, self.stream)

    def revert_to_wakeword(self):
        self.stream.exit()
    
    def is_alive(self): 
        if self.exc: 
            raise self.exc
        return True

    def run(self):
        self.quit_time = False
        while not self.stopped.wait(TIMEOUT):
            self.quit_time = True
            print("=======REVERT TO WAKEWORD=======")
            self.revert_to_wakeword()
            break

    def join(self):
        Thread.join(self)

class Tank():
    def __init__(self):
        self.language_code = 'en-US'  # a BCP-47 language tag

        self.porcupine = None
        self.sound = None
        self.audio_stream = None

        self.diarization_config = None

        self.listening = False

    def enable(self):
        self.audio_model = whisper.load_model("medium.en")
        print("===================streaming from openai whisper========================")
        
        self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_mac_v2_1_0.ppn'])
        # self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_linux_v2_1_0.ppn'])

        self.sound = pyaudio.PyAudio()

        self.audio_stream = sound.open(
                        rate=porcupine.sample_rate, # RATE
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=porcupine.frame_length, #CHUNK
                        )

        self.listening = False
        self.setup_IPC()

    def setup_IPC(self):
        """
        Sets up and enables the IPC connection to central with task name: textInput
        LEGACY: fake_kbd for victor
        """
        print("IPC CONNECTING: TEXTINPUT...")
        IPC.IPC_connect("textInput")

        # shouldn't need to define any of the messages anymore
        #  - should be handled by the interfaces functions
        # print("IPC DEFINE MSG: TEXTINPUT_START_MSG")
        # IPC.IPC_defineMsg(TEXTINPUT_START_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        # IPC.IPC_defineMsg(TEXTINPUT_TEXT_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        # IPC.IPC_defineMsg(TEXTINPUT_KEYPRESS_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        # IPC.IPC_defineMsg(TEXTINPUT_CLEAR_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        
    def publish_start_transcription(self):
        """
        Publish a start string to indicate someone is speaking
        """
        print("HEY TANK!")
        # IPC.IPC_publishData(TEXTINPUT_START_MSG, "start")
        TEXTINPUT_send_start()

    def publish_transcript(self, transcript):
        """
        Publish the transcript
        """
        print("PUBLISHING DATA")
        TEXTINPUT_send_input(transcript)

    def publish_keypress(self):
        """
        Publish a keypress value to indicate there is still someone present
        """
        IPC.IPC_publishData(TEXTINPUT_KEYPRESS_MSG, "keypress")

    def publish_clear_messages(self):
        """
        Publish a message to indicate the person has left, clears the previous person's history
        """
        # TODO determine what the clear message data is, create a function in chatGPT that clears the data
        print("CLEAR DATA HISTORY")
        # chatGPT.clearData()

        # publishes something to indicate that the person has left 
        TEXTINPUT_send_clear() # from the interfaces

    def terminate_IPC(self):
        """
        Disconnects task from central 
        """
        print("DISCONNECTING fake_kbd...")
        IPC.IPC_disconnect()

    def listen(self):
        print("connected...")
        while True:
            self.publish_IPC(1, 'hello world')
            pcm = self.audio_stream.read(self.porcupine.frame_length)
            pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)

            keyword_index = self.porcupine.process(pcm)
            
            if keyword_index >= 0:
                self.publish_start_transcription()
                self.listening = True

            if listening:
                print('attempting to connect with transcribe')
                audio_stream.stop_stream()
                audio_stream.close()

                stream = MicrophoneStream(RATE, CHUNK, audio_interface=sound)
                stream.enter()
                audio_generator = stream.generator()
                responses = audio_generator

                # Now, put the transcription responses to use.
                stop_flag = Event()
                stop_flag.clear()

                quit_auto = QuitThread(stop_flag, responses, stream)
                quit_auto.start()
                
                print("printing listening")
                self.listen_print_loop(responses, messages=messages, audio_model=audio_model, stop_flag=stop_flag, quit_auto=quit_auto)
                print("finished listening")
                print('exit transcription')

                self.audio_stream = sound.open(
                        rate=porcupine.sample_rate, # RATE
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=porcupine.frame_length, #CHUNK
                        )
                
                self.publish_clear_messages()
                self.listening = False

    def terminate(self):
        self.terminate_IPC()

        if self.porcupine is not None:
            self.porcupine.delete()
            self.porcupine = None

        if self.audio_stream is not None:
            self.audio_stream.close()
            self.audio_stream = None

        if self.sound is not None:
            self.sound.terminate()
            self.sound = None


    def listen_print_loop(self, responses, messages=None, audio_model=None, event=None, stop_flag=None, quit_auto=None):
        """Iterates through server responses and prints them.

        The responses passed is a generator that will block until a response
        is provided by the server.

        Each response may contain multiple results, and each result may contain
        multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
        print only the transcription for the top alternative of the top result.

        In this case, responses are provided for interim results as well. If the
        response is an interim one, print a line feed at the end of it, to allow
        the next result to overwrite it, until the response is a final one. For the
        final one, print a newline to preserve the finalized transcription.
        """
        try:
            for response in responses:
                if not stop_flag.is_set(): #if there is no stop flag then stop
                    stop_flag.set()

                if not response: #if there are no results
                    continue
                    
                # Display the transcription of the top alternative.
                audio_data = np.frombuffer(response, np.int16).flatten().astype(np.float32) / 32768.0
                result = audio_model.transcribe(audio_data, fp16=False, language='english')
                transcript = result["text"]

                print(transcript)
                # ask_chatgpt(transcript, messages)

                if stop_flag.is_set():
                    stop_flag.clear()
                    quit_auto.join()
                    quit_auto = quit_auto.clone()
                    quit_auto.start()
        except Exception as e:  
            print(f"caught exception {e}")
            return 
        finally:
            pass

def main(): 
    tank_listening = Tank()
    tank_listening.enable()

    try: 
        tank_listening.listen()
    except KeyboardInterrupt:
        print("Stopping....")
    finally: 
        tank_listening.terminate()

if __name__ == "__main__":
    main()