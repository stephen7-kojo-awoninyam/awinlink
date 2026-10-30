import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { Pressable, Text, View } from 'react-native';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { mergePage, nextPage } from '@/src/pagination';
import { colors } from '@/src/theme';

export function LoadMore<T>({ items, onChange, label = 'Load more' }: {
  items: T[]; onChange: Dispatch<SetStateAction<T[]>>; label?: string;
}) {
  const { user } = useAuth();
  const scope = `${user?.id}:${user?.role}`;
  const current = useRef({ items, scope });
  current.current = { items, scope };
  const context = useRef({ scope, epoch: {} });
  if (context.current.scope !== scope) context.current = { scope, epoch: {} };
  const active = useRef<object | null>(null);
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const next = nextPage(items);
  if (!next) return null;
  async function load() {
    if (active.current || !next) return;
    const source = items, identity = context.current.epoch, operation = {};
    active.current = operation;
    setBusy(true); setError('');
    try {
      const page = await apiRequest<T[]>(next);
      if (mounted.current && current.current.items === source && context.current.epoch === identity) {
        onChange(previous => previous === source ? mergePage(previous, page) : previous);
      }
    } catch (e) {
      if (mounted.current && current.current.items === source && context.current.epoch === identity) {
        setError(e instanceof Error ? e.message : 'Unable to load the next page.');
      }
    } finally { if (active.current === operation) active.current = null; if (mounted.current) setBusy(false); }
  }
  return <View>
    <Pressable accessibilityRole="button" disabled={busy} onPress={() => void load()} style={{ padding: 12, alignItems: 'center' }}>
      <Text style={{ color: colors.primary }}>{busy ? 'Loading…' : label}</Text>
    </Pressable>
    {!!error && <Text accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text>}
  </View>;
}
