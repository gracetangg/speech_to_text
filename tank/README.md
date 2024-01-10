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
- Tank closes the audio stream used for wakeword detection 

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
