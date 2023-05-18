import struct
import pyaudio
import pvporcupine

from threading import Thread
from threading import Event
from google.cloud import speech
from six.moves import queue

import IPC

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

class KEYBOARD_MESSAGE(IPC.IPCdata):
    _fields = ("player", "buffer")
    def __init__(self, player, buffer):
        self.player = player
        self.buffer = buffer

class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk, audio_interface=None, audio_stream=None):
        self._rate = rate
        self._chunk = chunk
        self._audio_interface = audio_interface
        # self._audio_stream = audio_stream
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
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
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
        print("=======REVERT TO WAKEWORD=======")
        self.stream.exit()
    
    def is_alive(self): 
        if self.exc: 
            raise self.exc
        return True

    def run(self):
        self.quit_time = False
        while not self.stopped.wait(TIMEOUT):
            self.quit_time = True
            self.revert_to_wakeword()
            break

    def join(self):
        Thread.join(self)

class Tank():
    def __init__(self):
        self.language_code = 'en-US'  # a BCP-47 language tag

        self.client = None
        self.config = None
        self.streaming_config = None

        self.porcupine = None
        self.sound = None
        self.audio_stream = None

        self.diarization_config = None

        self.listening = False

    def enable(self):
        self.client = speech.SpeechClient()
        self.diarization_config = speech.SpeakerDiarizationConfig(
            enable_speaker_diarization=True,
            min_speaker_count=1,
            max_speaker_count=10,
            )
        self.config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=RATE,
                        language_code=self.language_code,
                        diarization_config=self.diarization_config
                        )
        self.streaming_config = speech.StreamingRecognitionConfig(
                        config=self.config,
                        interim_results=True
                        )
        
        # TODO make porcupine for hey TANK 
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
        Sets up and enables the IPC connection to central with task name: fake_kbd
        """
        # TODO figure out what to connect to
        print("IPC CONNECTING: TEXTINPUT...")
        IPC.IPC_connect("fake_kbd")

        print("IPC DEFINE MSG: TEXTINPUT_START_MSG")
        IPC.IPC_defineMsg(TEXTINPUT_START_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_TEXT_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_KEYPRESS_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        IPC.IPC_defineMsg(TEXTINPUT_CLEAR_MSG, IPC.IPC_VARIABLE_LENGTH, TEXTINPUT_MESSAGE_FMT)
        
    def publish_start_transcription(self):
        """
        Publish a start string to indicate someone is speaking
        """
        print("HEY TANK!")
        IPC.IPC_publishData(TEXTINPUT_START_MSG, "start")

    def publish_transcript(self, transcript):
        """
        Publish the transcript
        """
        print("PUBLISHING DATA")
        IPC.IPC_publishData(TEXTINPUT_TEXT_MSG, transcript)

    def publish_keypress(self):
        """
        Publish a keypress value to indicate there is still someone present
        """
        IPC.IPC_publishData(TEXTINPUT_KEYPRESS_MSG, "keypress")

    def publish_clear_messages(self):
        """
        Publish a message to indicate the person has left, clears the previous person's history
        """
        # TODO determine what the clear message data is
        print("CLEAR DATA HISTORY")
        IPC.IPC_publishData(TEXTINPUT_CLEAR_MSG, "keypress")

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
                
            if not self.listening:
                continue

            # attempt to connect with transcribe here:
            self.audio_stream.stop_stream()
            self.audio_stream.close()

            stream = MicrophoneStream(RATE, CHUNK, audio_interface=self.sound)
            stream.enter()
            
            audio_generator = stream.generator()
            requests = (speech.StreamingRecognizeRequest(audio_content=content)
                        for content in audio_generator)

            responses = self.client.streaming_recognize(self.streaming_config, requests)

            # Now, put the transcription responses to use.
            stop_flag = Event()
            stop_flag.clear()

            quit_auto = QuitThread(stop_flag, responses, stream)
            quit_auto.start()
            
            # print any words to transcribe
            self.listen_print_loop(responses, stop_flag=stop_flag, quit_auto=quit_auto)

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


    def listen_print_loop(self, responses, event=None, stop_flag=None, quit_auto=None):
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
            num_chars_printed = 0
            for response in responses:
                
                if not stop_flag.isSet(): #if there is no stop flag then stop
                    stop_flag.set()

                if not response.results: #if there are no results
                    continue

                # The `results` list is consecutive. For streaming, we only care about
                # the first result being considered, since once it's `is_final`, it
                # moves on to considering the next utterance.
                result = response.results[0]
                if not result.alternatives: #if there are no alternatives 
                    continue
                    
                # Display the transcription of the top alternative.
                transcript = result.alternatives[0].transcript
                wordlist = response.results[-1].alternatives[0].words

                # Display interim results, but with a carriage return at the end of the
                # line, so subsequent lines will overwrite them.
                #
                # If the previous result was longer than this one, we need to print
                # some extra spaces to overwrite the previous result
                overwrite_chars = ' ' * (num_chars_printed - len(transcript))

                if not result.is_final:
                    num_chars_printed = len(transcript)

                else:
                    print(transcript)
                    player = 1
                    self.publish_IPC(player, transcript)

                    for word in wordlist: 
                        word_speaker = f"{word.word} speaker: {word.speaker_tag}"
                        print(word_speaker)
                        self.publish_IPC(player, word_speaker)
                    
                    if stop_flag.isSet():
                        stop_flag.clear()
                        quit_auto.join()
                        quit_auto = quit_auto.clone()
                        quit_auto.start()
                    num_chars_printed = 0
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