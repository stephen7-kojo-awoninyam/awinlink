(function (root) {
    'use strict';
    const formats = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const recordingFormat = {
        select(Recorder) {
            return formats.find(type => typeof Recorder.isTypeSupported === 'function' && Recorder.isTypeSupported(type)) || '';
        },
        extension(type) {
            const mime = type.split(';')[0].trim().toLowerCase();
            return ({'audio/mp4': 'mp4', 'audio/ogg': 'ogg', 'audio/webm': 'webm', 'audio/wav': 'wav', 'audio/mpeg': 'mp3'})[mime] || 'bin';
        }
    };
    if (typeof module === 'object') module.exports = recordingFormat;
    else root.recordingFormat = recordingFormat;
})(typeof window === 'object' ? window : globalThis);
