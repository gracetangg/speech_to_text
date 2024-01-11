# Tank's FasterWhisper Speech to Text Integration 
This folder contains the pipeline for speech-to-text processing and broadcasting to Tank (the Roboceptionist). 

# `tank.py`
## `Tank`
This class is responsible for handling Tanks main routine: 
- If wakeword "Hey Tank" is active:
  - Tank begins listening for audio data
  - Processes audio data (speech-to-text pipeline using FasterWhisper)
  - Publishing speech-to-text data to robocept software
- Else: Wait for wakeword "Hey Tank"
### Overall workflow 
Tank opens a `pyaudio.PyAudio` object and an audio stream object. This audio is processed by `Porcupine`, 
a wakeword engine. \\
If wakeword: 
- Publish the start message for Tank interaction
- Tank closes the audio stream used for wakeword detection
- Create a MicrophoneStream object and retrieve the generator object, `responses`
- Create a QuitThread object
- Start the listening loop
  - For each non-empty audio chunk generated, translate chunk into audio data array
  - Using FasterWhisper, transcribe the audio data (note params were chosen to avoid "hallucinations" (over fitting from OpenAI results in transcription of empty noise)
  - If there are results from the transcript, then publish
- Listening loop will exit when Tank publishes his abort interaction message
- Reset to the wakeword by closing the MicrophoneStream and opening a new audio stream (loop repeats)

### Legacy Wakeword Reactivation 
Previously, wakeword reactivation would be triggered after a timeout. This was done by having `QuitThread` take in a `stop_event = threading.Event()`. We would set the event if it hadn't been set in the main thread and "reset" the event after the transcription had been published. The quit thread would detect if there was a timeout (i.e. the event HADN'T been set in a given time)
``` python
class QuitThread(Thread):
    def __init__(self, event=None, stream=None):
        Thread.__init__(self)
        self.stopped = event
        self.exc = None
        self.stream = stream
        self.stop = False

    def clone(self):
        return QuitThread(self.stopped, self.stream)

    def revert_to_wakeword(self):
        if self.stream:
            self.stream.exit()

    def run(self):
        while not self.stopped.wait(TIMEOUT):
            print("=======REVERT TO WAKEWORD=======")
            self.revert_to_wakeword()
            break

    def join(self):
        Thread.join(self)

...

class Tank():
  ...
  
  def listen_print_loop(self, responses, audio_model=None, stop_flag=None, quit_auto=None):
        try:
            for response in responses:
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
                #     # log_prob_threshold=-0.5,
                #     no_speech_threshold=0.2,
                #     fp16=False, 
                #     language='english')
                # transcript = result["text"]

                result, _ = audio_model.transcribe(
                    audio=audio_data, 
                    temperature=0.0,
                    best_of=0,
                    beam_size=1,
                    patience=1,
                    length_penalty=1,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-0.25,
                    no_speech_threshold=0.2)
                transcript = "\n".join([seg.text for seg in list(result)])

                if not result or not transcript: 
                    continue

                if not stop_flag.is_set(): #if there is no stop flag then stop
                    stop_flag.set()

                print(transcript)
                self.publish_keypress()
                self.publish_transcript(transcript)
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

```

### FasterWhisper vs. OpenAI 
From experimentation OpenAI Whisper proved to take a significant time to complete the audio transcription, which hinders the robot-human interaction. We found that FasterWhisper not only had a faster transcription time, it also had a faster start-up/model loading time and was more tolerant to hallucinations (less overfit than OpenAI). More info [here](https://github.com/SYSTRAN/faster-whisper)

## `MicrophoneStream`
This class opens a *new* recording stream as a generator, yielding audio chunks. The audio stream data continuously fills a buffer.
The application will retrieve audio chunks from this buffer. 
Parameters: 
- `rate`: audio sampling rate
- `chunk`: audio chunk size
- `audio_interface`: instanitated `pyAudio` instance that initializes `PortAudio` resources

## `QuitThread`
Thread that handles listening for new data published to `SendSignal` message (thread subscribed to `SendSignal`). 
This will handle exiting the listen routine (audio stream) and revert Tank back to waiting for a wakeword before processing any audio data. 

---
# Future
There are still things to work on!
1. How to turn off transcription when Tank is responding: Tank should be publishing when responses start and end. Using this (through a subscription in Python), we should pause any transcription/don't process any audio data in the buffer while Tank is responding. Otherwise the program starts transcribing Tank!
2. How to mitigate the select statement from `IPC.IPC_Listen()`: When listening for subscriptions, the select statement blocks the audio stream from fetching data for processing. If we increase the listen timeout, the audio stream is blocked. If we decrease the liten timeout, `QuitThread` doesn't always catch Tank's abort interact message, and we never return to the wakeword
3. Change some of Tank's behavior to account for speech interaction: Tank currently speaks/prompts the user to hurry up typing, which would be a major interruption of the user speaking. 
