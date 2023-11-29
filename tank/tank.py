import struct
import pvporcupine

from threading import Thread
from threading import Event
from six.moves import queue
from scipy import signal 
import numpy as np
import pyaudio
import whisper

import faster_whisper

import IPC
# import textinputInterface # comes from the cpp library hopefully...

# constants for TEXTINPUT: 
TEXTINPUT_Start_MSG = "TEXTINPUT_Start_MSG"
TEXTINPUT_Start_MSG_FMT = "string"
TEXTINPUT_Keypress_MSG = "TEXTINPUT_Keypress_MSG"
TEXTINPUT_Keypress_MSG_FMT = "string"
TEXTINPUT_Text_MSG = "TEXTINPUT_Text_MSG"
TEXTINPUT_Text_MSG_FMT = "string"
TEXTINPUT_Clear_MSG = "TEXTINPUT_Clear_MSG"
TEXTINPUT_Clear_MSG_FMT = "string"

SPEECHINPUT_Start_MSG = "SPEECHINPUT_Start_MSG"
SPEECHINPUT_Start_MSG_FMT = "string"
SPEECHINPUT_Keypress_MSG = "SPEECHINPUT_Keypress_MSG"
SPEECHINPUT_Keypress_MSG_FMT = "string"
SPEECHINPUT_Text_MSG = "SPEECHINPUT_Text_MSG"
SPEECHINPUT_Text_MSG_FMT = "string"
SPEECHINPUT_Clear_MSG = "SPEECHINPUT_Clear_MSG"
SPEECHINPUT_Clear_MSG_FMT = "string"

SEND_SIGNAL_MSG = "SendSignal"
SEND_SIGNAL_MSG_FMT = "string"

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
TIMEOUT = 60

access_key = "YmjdiYjeRf9LwFBJCFxf299XxeiDoMRITiAjyvHcvc/RlOI1JLCwZA==" 

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

        # Filter parameters
        self._filter_cutoff = 500 
        self._filter_order = 3 

        # Create a low-pass filter
        nyquist = 0.5 * self._rate
        normal_cutoff = self._filter_cutoff / nyquist
        self._b, self._a = signal.butter(self._filter_order, normal_cutoff, btype='low', analog=False)

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
    
    def _apply_filter(self, audio_data):
        # Apply the filter to the audio data
        filtered_data = signal.lfilter(self._b, self._a, audio_data)
        return filtered_data

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

            # audio_data = np.frombuffer(b''.join(data), dtype=np.int16).flatten().astype(np.float32) / 32768.0
            # filtered_audio = self._apply_filter(audio_data)
            # yield filtered_audio.tobytes()

            yield b''.join(data)

class QuitThread(Thread):
    def __init__(self, event, responses, stream):
        Thread.__init__(self)
        self.stopped = event
        self.responses = responses
        self.exc = None
        self.stream = stream

        IPC.IPC_subscribeData("SendSignal", self.process_signal, None)

    def clone(self):
        return QuitThread(self.stopped, self.responses, self.stream)
    
    def process_signal(self, msg_ref, call_data, client_data):
        # SendSignal
        # HEAD_send_signal("interaction:aborted");
        # HEAD_send_signal("interaction:end");
        if call_data == "interaction:aborted" or call_data == "interaction:end": 
            print("SET STOPPED")
            self.stopped.set()

    def revert_to_wakeword(self):
        print("HERE")
        self.stream.exit()
    
    def is_alive(self): 
        if self.exc: 
            raise self.exc
        return True

    def run(self):
        while (IPC.IPC_isConnected() and not self.stopped.is_set()): 
            IPC.IPC_listen(250)
        
        print("=======REVERT TO WAKEWORD=======")
        self.revert_to_wakeword()
        
        # self.stopped.wait()
        # print("=======REVERT TO WAKEWORD=======")
        # self.revert_to_wakeword()

        while not self.stopped.wait(TIMEOUT):
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
        # self.audio_model = whisper.load_model("medium.en")
        self.audio_model = faster_whisper.WhisperModel("medium.en", device="cpu", compute_type="int8")
        print("===================streaming from openai whisper========================")
        
        # self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_mac_v2_1_0.ppn'])
        self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_linux_v2_1_0.ppn'])

        self.sound = pyaudio.PyAudio()

        self.audio_stream = self.sound.open(
                        rate=self.porcupine.sample_rate, # RATE
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=self.porcupine.frame_length, #CHUNK
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
        print("IPC DEFINE MSG: SPEECHINPUT_START_MSG")
        IPC.IPC_defineMsg(TEXTINPUT_Start_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_Start_MSG_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_Text_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_Text_MSG_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_Keypress_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_Keypress_MSG_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_Clear_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_Clear_MSG_FMT)

        IPC.IPC_defineMsg(SPEECHINPUT_Start_MSG,    IPC.IPC_VARIABLE_LENGTH, SPEECHINPUT_Start_MSG_FMT)
        IPC.IPC_defineMsg(SPEECHINPUT_Text_MSG,     IPC.IPC_VARIABLE_LENGTH, SPEECHINPUT_Text_MSG_FMT)
        IPC.IPC_defineMsg(SPEECHINPUT_Keypress_MSG, IPC.IPC_VARIABLE_LENGTH, SPEECHINPUT_Keypress_MSG_FMT)
        IPC.IPC_defineMsg(SPEECHINPUT_Clear_MSG,    IPC.IPC_VARIABLE_LENGTH, SPEECHINPUT_Clear_MSG_FMT)
        IPC.IPC_defineMsg(SEND_SIGNAL_MSG,          IPC.IPC_VARIABLE_LENGTH, SEND_SIGNAL_MSG_FMT)
        
    def publish_start_transcription(self):
        """
        Publish a start string to indicate someone is speaking
        """
        print("HEY TANK!")
        IPC.IPC_publishData(TEXTINPUT_Start_MSG, "start")
        # IPC.IPC_publishData(SPEECHINPUT_Start_MSG, "start")

    def publish_transcript(self, transcript):
        """
        Publish the transcript
        """
        print("PUBLISHING DATA")
        IPC.IPC_publishData(TEXTINPUT_Text_MSG, transcript)
        # IPC.IPC_publishData(SPEECHINPUT_Text_MSG, transcript)


    def publish_keypress(self):
        """
        Publish a keypress value to indicate there is still someone present
        """
        IPC.IPC_publishData(TEXTINPUT_Keypress_MSG, "keypress")
        # IPC.IPC_publishData(SPEECHINPUT_Keypress_MSG, "keypress")

    def publish_clear_messages(self):
        """
        Publish a message to indicate the person has left, clears the previous person's history
        """
        # TODO determine what the clear message data is, create a function in chatGPT that clears the data
        print("CLEAR DATA HISTORY")
        IPC.IPC_publishData(TEXTINPUT_Clear_MSG, "");
        # IPC.IPC_publishData(SPEECHINPUT_Clear_MSG, "");

    def terminate_IPC(self):
        """
        Disconnects task from central 
        """
        print("DISCONNECTING speech_input...")
        IPC.IPC_disconnect()

    def listen(self):
        print("connected...")
        self.publish_transcript("Hello world!")
        while True:
            pcm = self.audio_stream.read(self.porcupine.frame_length)
            pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)

            keyword_index = self.porcupine.process(pcm)
            
            if keyword_index >= 0:
                self.publish_start_transcription()
                self.listening = True

            if self.listening:
                print('attempting to connect with transcribe')
                self.audio_stream.stop_stream()
                self.audio_stream.close()

                stream = MicrophoneStream(RATE, CHUNK, audio_interface=self.sound)
                stream.enter()
                responses = stream.generator()

                # Now, put the transcription responses to use.
                stop_flag = Event()
                stop_flag.clear()

                quit_auto = QuitThread(stop_flag, responses, stream)
                quit_auto.start()
                
                print("printing listening")
                self.listen_print_loop(responses, audio_model=self.audio_model, stop_flag=stop_flag, quit_auto=quit_auto)
                print("finished listening")
                print('exit transcription')

                self.audio_stream = self.sound.open(
                        rate=self.porcupine.sample_rate, # RATE
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=self.porcupine.frame_length, #CHUNK
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


    def listen_print_loop(self, responses, audio_model=None, stop_flag=None, quit_auto=None):
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
                print("RESPONSE")
                if not response:
                    continue
                    
                # Display the transcription of the top alternative.
                audio_data = np.frombuffer(response, np.int16).flatten().astype(np.float32) / 32768.0

                # result = audio_model.transcribe(
                #     audio_data, 
                #     verbose=False, 
                #     temperature=0,
                #     task='transcribe',
                #     best_of=None,
                #     beam_size=None,
                #     patience=None,
                #     length_penalty=None,
                #     suppress_tokens="-1",
                #     condition_on_previous_text=False,
                #     compression_ratio_threshold=2.4,
                #     log_prob_threshold=-0.5,
                #     no_speech_threshold=0.2,
                #     fp16=False, 
                #     language='english')
                # transcript = result["text"]

                result, _ = audio_model.transcribe(
                    audio=audio_data, 
                    temperature=0.0,
                    best_of=1,
                    beam_size=1,
                    patience=1,
                    length_penalty=1,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-0.5,
                    no_speech_threshold=0.2)
                transcript = "\n".join([seg.text for seg in list(result)])

                # if not result or not transcript: 
                #     continue

                # if not stop_flag.is_set(): #if there is no stop flag then stop
                #     stop_flag.set()

                print(transcript)
                self.publish_transcript(transcript)
                # ask_chatgpt(transcript, messages)

                # if stop_flag.is_set():
                #     stop_flag.clear()
                #     quit_auto.join()
                #     quit_auto = quit_auto.clone()
                #     quit_auto.start()

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
