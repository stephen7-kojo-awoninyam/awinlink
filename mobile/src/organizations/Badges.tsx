import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { Link, useFocusEffect } from 'expo-router';
import { rosterPages, TalentTag } from './rosters';
import { ui } from '@/src/components/Page';

export function OrganizationBadges({ talentId, organizationId }: { talentId?: number; organizationId?: number }) {
  const [rows, setRows] = useState<TalentTag[]>([]);
  const [error, setError] = useState('');
  useFocusEffect(useCallback(() => {
    let active = true;
    setRows([]); setError('');
    const path = talentId ? `organizations/talent-tags/profile/${talentId}/` : `organizations/${organizationId}/roster/public/`;
    void rosterPages<TalentTag>(path).then(data => { if (active) setRows(data); })
      .catch(() => { if (active) setError('Affiliations could not be loaded.'); });
    return () => { active = false; };
  }, [talentId, organizationId]));
  return <View style={{ gap: 8 }}>
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    {rows.map(row => <View key={row.id} style={ui.card}>
      {organizationId && row.talent_id ? <Link href={{ pathname: '/talent/[id]', params: { id: row.talent_id } }}>{row.name}</Link> : <Text>{row.organization_name}</Text>}
      <Text>{row.tag}{row.roster ? ` · ${row.roster}` : ''} · Talent confirmed</Text>
    </View>)}
  </View>;
}
