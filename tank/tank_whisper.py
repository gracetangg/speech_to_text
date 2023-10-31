# *********** THIS ONE IS FOR TANK USES WHISPER INSTEAD OF GOOGLE CLOUD **************

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

# constants for KBD: 
PLAYER_FORMAT               = "int"
KEYBOARD_MESSAGE_MSG        = "keyboard message"
KEYBOARD_MESSAGE_FMT        = f"{{{PLAYER_FORMAT}, string}}"
KEYBOARD_MESSAGE_BB         = "keyboard_message_bb"

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
TIMEOUT = 15

porcupine = None
sound = None
audio_stream = None

# access_key_mac = "YmjdiYjeRf9LwFBJCFxf299XxeiDoMRITiAjyvHcvc/RlOI1JLCwZA==" 
access_key = "75JC2IEZ9LRmieC18yAK+waN3fILDT2jwiaSQGZSCPmxlPm1+jLAcw=="

victor_api = "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"

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

def ask_chatgpt(transcript, messages):
    if transcript:
        messages.append(
                {"role": "user", "content": f"{transcript}."},
        )
        chat_completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages
        )
        answer = chat_completion.choices[0].message.content
        print(f"ChatGPT: {answer}")
        messages.append({"role": "assistant", "content": answer})

def detect_speakers(wordlist):
    max_timestamp = 0
    speakers = {}
    for word in wordlist: 
        if word.start_time.seconds > prev_timestamp:
            if word.speaker_tag not in speakers: 
                speakers[word.speaker_tag] = ""
            speakers[word.speaker_tag] = f"{speakers[word.speaker_tag]} {word.word}"
            max_timestamp = max(max_timestamp, word.end_time.seconds)
    
    for speaker in speakers: 
        print(f"{speaker} {speakers[speaker]}")
    
    prev_timestamp = max_timestamp
    return prev_timestamp

def listen_print_loop(responses, messages=None, audio_model=None, event=None, stop_flag=None, quit_auto=None):
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
    prev_timestamp = 0
    try:
        num_chars_printed = 0
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
    audio_model = whisper.load_model("medium.en")
    print("===================streaming from openai whisper========================")
    
    porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_mac_v2_1_0.ppn'])
    # porcupine = pvporcupine.create(access_key=access_key, keyword_paths=['./hey-victor_en_linux_v2_1_0.ppn'])

    sound = pyaudio.PyAudio()

    audio_stream = sound.open(
                    rate=porcupine.sample_rate, # RATE
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length, #CHUNK
                    )

    listening = False

    # openai.api_key = os.environ['api_key']
    openai.api_key = victor_api
    messages = [
            {"role": "system", "content": "You are a robot receptionist named Tank. You are not powered by Artificial Intelligence."},
    ]

    try:
        while True:
            pcm = audio_stream.read(porcupine.frame_length)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

            keyword_index = porcupine.process(pcm)

            if keyword_index >= 0:
                listening = True
                print("hey victor!!")
                
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
                listen_print_loop(responses, messages=messages, audio_model=audio_model, stop_flag=stop_flag, quit_auto=quit_auto)
                print("finished listening")
                print('exit transcription')

                audio_stream = sound.open(
                        rate=porcupine.sample_rate, # RATE
                        channels=1,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=porcupine.frame_length, #CHUNK
                        )
                listening = False
                
                
    except KeyboardInterrupt:
        print("Stopping....")

    finally:
        print("Closing...")
        if porcupine is not None:
            porcupine.delete()

        if audio_stream is not None:
            audio_stream.close()

        if sound is not None:
            sound.terminate()


def main2():
    openai.api_key = victor_api
    messages = [
            {"role": "system", "content": "You are a robot receptionist named Tank. You are not powered by Artificial Intelligence."},
    ]
    while True:
        transcript = input()
        ask_chatgpt(transcript, messages)   

    
if __name__ == "__main__": 
    main()
