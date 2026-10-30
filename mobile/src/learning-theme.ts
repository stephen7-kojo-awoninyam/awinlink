import { StyleSheet } from 'react-native';

export const learningColors = { blue: '#0056d2', ink: '#152542', muted: '#526179', line: '#dce5f0', pale: '#eef5ff', white: '#ffffff' };

export const learningStyles = StyleSheet.create({
  hero: { backgroundColor: learningColors.pale, borderColor: '#d8e6fb', borderWidth: 1, borderRadius: 20, padding: 24, gap: 14 },
  eyebrow: { color: '#385e91', fontSize: 10, fontWeight: '800', letterSpacing: 1.5 },
  heroTitle: { color: learningColors.ink, fontSize: 30, lineHeight: 37, fontWeight: '800', letterSpacing: -0.7, flexShrink: 1 },
  accent: { color: learningColors.blue },
  body: { color: learningColors.muted, fontSize: 14, lineHeight: 22 },
  sectionHeader: { gap: 6, marginTop: 12 },
  sectionTitle: { color: learningColors.ink, fontSize: 22, fontWeight: '800', letterSpacing: -0.4 },
  card: { backgroundColor: learningColors.white, borderColor: learningColors.line, borderWidth: 1, borderRadius: 16, padding: 20, gap: 12, minWidth: 0 },
  cardTitle: { color: learningColors.ink, fontSize: 17, fontWeight: '800', lineHeight: 24 },
  row: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 10 },
  button: { minHeight: 48, borderRadius: 8, paddingVertical: 13, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: learningColors.blue },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '800', textAlign: 'center' },
  secondary: { backgroundColor: '#fff', borderColor: '#bacfec', borderWidth: 1 },
  secondaryText: { color: learningColors.blue, fontSize: 14, fontWeight: '800', textAlign: 'center' },
  badge: { color: learningColors.blue, backgroundColor: learningColors.pale, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 6, alignSelf: 'flex-start', fontSize: 11, fontWeight: '800' },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: '#e4eeff', alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 20, fontWeight: '800', color: learningColors.blue },
  copy: { flex: 1, minWidth: 120, gap: 5 },
  track: { height: 8, borderRadius: 4, backgroundColor: '#e4edfb', overflow: 'hidden' },
  fill: { height: 8, borderRadius: 4, backgroundColor: learningColors.blue },
});
