import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { Link, useFocusEffect } from 'expo-router';
import { rosterPages, TalentTag } from './rosters';
import { ui } from '@/src/components/Page';

export function OrganizationBadges({ talentId, organizationId, userId }: { talentId?: number; organizationId?: number; userId?: number }) {
  const [rows, setRows] = useState<TalentTag[]>([]);
  const [error, setError] = useState('');
  useFocusEffect(useCallback(() => {
    let active = true;
    setRows([]); setError('');
    const path = userId ? `organizations/profile-badges/${userId}/` : talentId ? `organizations/talent-tags/profile/${talentId}/` : organizationId ? `organizations/${organizationId}/roster/public/` : null;
    if (!path) return () => { active = false; };
    void rosterPages<TalentTag>(path).then(data => { if (active) setRows(data); })
      .catch(() => { if (active) setError('Affiliations could not be loaded.'); });
    return () => { active = false; };
  }, [talentId, organizationId, userId]));
  return <View style={{ gap: 8 }}>
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    {rows.map(row => <View key={row.id} style={ui.card}>
      {organizationId ? row.talent_id ? <Link href={{ pathname: '/talent/[id]', params: { id: row.talent_id } }}>{row.profile_name || row.name}</Link> : <Text>{row.profile_name || row.name}</Text> : <Text>{row.organization_name}</Text>}
      <Text>{row.tag}{row.roster ? ` · ${row.roster}` : ''} · {row.profile_type === 'COACH' ? 'Coach' : row.profile_type === 'SCOUT' ? 'Scout' : 'Talent'} confirmed</Text>
    </View>)}
  </View>;
}
