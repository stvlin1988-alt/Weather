/**
 * VoiceInput — wraps Web Speech API for transcription into a textarea
 * Usage: const voice = new VoiceInput(textareaElement);
 *        voice.start(); voice.stop();
 */
class VoiceInput {
  constructor(targetElement) {
    this.target = targetElement;
    this.isRecording = false;
    this.recognition = null;
    this._init();
  }

  _init() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('此瀏覽器不支援 Web Speech API');
      return;
    }
    this.recognition = new SpeechRecognition();
    this.recognition.lang = 'zh-TW';
    this.recognition.continuous = true;
    this.recognition.interimResults = true;

    let finalTranscript = '';
    this.recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalTranscript += t;
        else interim = t;
      }
      this.target.value = (this._baseContent || '') + finalTranscript + interim;
      this.target.dispatchEvent(new Event('input'));
    };

    this.recognition.onend = () => {
      if (this.isRecording) this.recognition.start(); // auto restart
    };
  }

  start() {
    if (!this.recognition) return;
    this._baseContent = this.target.value;
    this.isRecording = true;
    this.recognition.start();
  }

  stop() {
    if (!this.recognition) return;
    this.isRecording = false;
    this.recognition.stop();
  }
}
