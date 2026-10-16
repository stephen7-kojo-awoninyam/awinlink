import { useMemo, useRef, useState } from 'react';
import { PanResponder, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { colors } from '@/src/theme';
import { objectAt, point, sampledPoints, uuid, type Board, type BoardObject } from './client';

type Props = { board: Board | null; connected: boolean; command: (action: string, payload?: unknown) => Promise<void>; onError: (error: unknown) => void };
const tools = ['stroke', 'text', 'rectangle', 'ellipse', 'line', 'erase'];
function Segment({ a, b, color, width }: { a: number[]; b: number[]; color: string; width: number }) {
  const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
  return <View pointerEvents="none" style={{ position: 'absolute', backgroundColor: color, borderRadius: width,
    width: Math.max(width, length), height: width, left: (a[0] + b[0]) / 2 - Math.max(width, length) / 2,
    top: (a[1] + b[1]) / 2 - width / 2, transform: [{ rotate: `${Math.atan2(dy, dx)}rad` }] }} />;
}
function Shape({ object, width, height, maximum }: { object: BoardObject; width: number; height: number; maximum: number }) {
  const x = (object.x || 0) * width, y = (object.y || 0) * height;
  if (object.kind === 'text') return <Text pointerEvents="none" style={{ position: 'absolute', left: x, top: y,
    color: object.color, fontSize: (object.size || .025) * width, includeFontPadding: false }}>{object.text}</Text>;
  if (object.kind === 'stroke' || object.kind === 'ellipse') {
    const points = object.kind === 'stroke' ? sampledPoints(object.points || [], maximum) : Array.from({ length: 33 }, (_, index) => {
      const angle = index / 32 * Math.PI * 2;
      return [(object.x || 0) + (object.w || 0) / 2 * (1 + Math.cos(angle)), (object.y || 0) + (object.h || 0) / 2 * (1 + Math.sin(angle))];
    });
    return <>{points.slice(1).map((p, index) => <Segment key={index}
      a={[points[index][0] * width, points[index][1] * height]} b={[p[0] * width, p[1] * height]}
      color={object.color} width={object.width * width} />)}</>;
  }
  if (object.kind === 'line') return <Segment a={[x, y]} b={[x + (object.w || 0) * width, y + (object.h || 0) * height]} color={object.color} width={object.width * width} />;
  return <View pointerEvents="none" style={{ position: 'absolute', left: x, top: y, width: (object.w || 0) * width,
    height: (object.h || 0) * height, borderColor: object.color, borderWidth: object.width * width,
    borderRadius: 0 }} />;
}
export function Whiteboard({ board, connected, command, onError }: Props) {
  const [tool, setTool] = useState('stroke'), [text, setText] = useState(''), [color, setColor] = useState('#2458d3');
  const [size, setSize] = useState({ width: 300, height: 240 }), [preview, setPreview] = useState<BoardObject | null>(null);
  const drawing = useRef<{ start: number[]; object: BoardObject } | null>(null);
  const current = useRef({ board, connected, tool, text, color, size, command, onError });
  current.current = { board, connected, tool, text, color, size, command, onError };
  const perform = (action: string, payload?: unknown) => current.current.command(action, payload).catch(current.current.onError);
  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => !!current.current.board?.can_edit && current.current.connected,
    onMoveShouldSetPanResponder: () => !!drawing.current,
    onPanResponderGrant: event => {
      const props = current.current;
      const [x, y] = point(event.nativeEvent.locationX / props.size.width, event.nativeEvent.locationY / props.size.height);
      if (props.tool === 'erase') { const id = objectAt(props.board?.objects || {}, x, y); if (id) void perform('erase', { ids: [id] }); return; }
      const object: BoardObject = { id: uuid(), kind: props.tool, color: props.color, width: .004 };
      if (props.tool === 'text') { if (props.text.trim()) void perform('add', { ...object, x, y, text: props.text, size: .025 }); return; }
      Object.assign(object, props.tool === 'stroke' ? { points: [[x, y], [x, y]] } : { x, y, w: 0, h: 0 });
      drawing.current = { start: [x, y], object }; setPreview({ ...object });
    },
    onPanResponderMove: event => {
      const props = current.current, draw = drawing.current;
      if (!draw || !props.board?.can_edit || !props.connected) { drawing.current = null; setPreview(null); return; }
      const [x, y] = point(event.nativeEvent.locationX / props.size.width, event.nativeEvent.locationY / props.size.height);
      if (draw.object.kind === 'stroke') { if (draw.object.points!.length < 2048) draw.object.points!.push([x, y]); }
      else if (draw.object.kind === 'line') { draw.object.w = x - draw.start[0]; draw.object.h = y - draw.start[1]; }
      else { draw.object.x = Math.min(x, draw.start[0]); draw.object.y = Math.min(y, draw.start[1]); draw.object.w = Math.abs(x - draw.start[0]); draw.object.h = Math.abs(y - draw.start[1]); }
      setPreview({ ...draw.object });
    },
    onPanResponderRelease: () => { const draw = drawing.current; drawing.current = null; setPreview(null);
      if (draw && current.current.board?.can_edit && current.current.connected) void perform('add', draw.object); },
    onPanResponderTerminate: () => { drawing.current = null; setPreview(null); },
  }), []);
  const editable = !!board?.can_edit && connected;
  const maximum = Math.min(128, Math.max(2, Math.floor(4000 / Math.max(1,
    Object.values(board?.objects || {}).filter(object => object.kind === 'stroke').length))));
  return <View style={styles.panel}>
    <Text style={styles.heading}>Whiteboard</Text><Text style={styles.hint}>{!connected ? 'Waiting for classroom connection' : editable ? 'Editing enabled' : 'View only — your host controls editing'}</Text>
    <View style={styles.tools}>{tools.map(item => <Pressable accessibilityRole="button" accessibilityState={{ selected: tool === item, disabled: !editable }} key={item} disabled={!editable} onPress={() => setTool(item)} style={[styles.chip, tool === item && styles.selected]}><Text>{item === 'stroke' ? 'Draw' : item}</Text></Pressable>)}</View>
    <View style={styles.tools}>{['#2458d3', '#172033', '#b42318', '#15803d'].map(item => <Pressable accessibilityLabel={`Draw in ${item}`} accessibilityRole="button" key={item} disabled={!editable} onPress={() => setColor(item)} style={[styles.swatch, { backgroundColor: item, borderWidth: item === color ? 3 : 0 }]} />)}
      <Pressable accessibilityRole="button" disabled={!editable} onPress={() => void perform('undo')} style={styles.chip}><Text>Undo</Text></Pressable>
      {board?.can_manage && <Pressable accessibilityRole="button" disabled={!connected} onPress={() => void perform('clear')} style={styles.chip}><Text>Clear</Text></Pressable>}
    </View>
    {tool === 'text' && <TextInput accessibilityLabel="Text to place on board" placeholder="Type text, then tap the board" value={text} maxLength={2000} editable={editable} onChangeText={setText} style={styles.input} />}
    <View {...responder.panHandlers} accessibilityLabel="Shared whiteboard" style={styles.canvas} onLayout={event => setSize(event.nativeEvent.layout)}>
      {Object.values(board?.objects || {}).map(object => <Shape key={object.id} object={object} width={size.width} height={size.height} maximum={maximum} />)}
      {editable && preview && <Shape object={preview} width={size.width} height={size.height} maximum={128} />}
    </View>
    <Text style={styles.hint}>Drag to draw. Tap for text or object erasing. Undo applies to your latest change.</Text>
    {Object.values(board?.objects || {}).filter(object => object.kind === 'text').map(object => <Text key={`accessible-${object.id}`} style={styles.hint}>{object.text}</Text>)}
  </View>;
}
const styles = StyleSheet.create({ panel: { backgroundColor: colors.surface, borderRadius: 14, padding: 12, gap: 10 }, heading: { color: colors.ink, fontSize: 17, fontWeight: '800' }, hint: { color: colors.muted, fontSize: 12 }, tools: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 }, chip: { padding: 8, borderRadius: 8, backgroundColor: colors.softBlue }, selected: { borderColor: colors.primary, borderWidth: 1 }, swatch: { width: 30, height: 30, borderRadius: 15, borderColor: '#8e9fb9' }, canvas: { backgroundColor: '#fff', height: 240, overflow: 'hidden', borderColor: colors.border, borderWidth: 1 }, input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10 } });
