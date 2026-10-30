export type CaptionCue = { start: number; end: number; text: string };

function seconds(value: string) {
  const parts = value.split(':');
  const tail = parts.pop()!;
  const [whole, millis = '0'] = tail.split('.');
  const second = Number(whole) + Number(`0.${millis}`);
  return parts.reduce((total, part) => total * 60 + Number(part), 0) * 60 + second;
}

export function parseWebVtt(input: string): CaptionCue[] {
  const text = input.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  if (!text.startsWith('WEBVTT\n')) throw new Error('Invalid WebVTT file.');
  const cues: CaptionCue[] = [];
  for (const block of text.slice(text.indexOf('\n\n') + 2).split(/\n[ \t]*\n/)) {
    const lines = block.split('\n');
    if (!block.trim() || lines[0].startsWith('NOTE')) continue;
    const timingIndex = lines[0].includes('-->') ? 0 : 1;
    const match = lines[timingIndex]?.match(/^((?:\d{2,}:)?[0-5]?\d:[0-5]\d\.\d{3})\s+-->\s+((?:\d{2,}:)?[0-5]?\d:[0-5]\d\.\d{3})(?:\s+.*)?$/);
    if (!match || cues.length >= 10000) throw new Error('Invalid caption cue.');
    const cueText = lines.slice(timingIndex + 1).join('\n').replace(/<[^>]*>/g, '').trim();
    if (!cueText || cueText.length > 5000) throw new Error('Invalid caption text.');
    const start = seconds(match[1]), end = seconds(match[2]);
    if (end <= start) throw new Error('Invalid caption cue.');
    cues.push({ start, end, text: cueText });
  }
  return cues;
}
