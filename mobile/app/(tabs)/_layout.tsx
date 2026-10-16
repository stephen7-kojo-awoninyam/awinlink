import { SymbolView } from 'expo-symbols';
import { Redirect, Tabs } from 'expo-router';

import { useAuth } from '@/src/auth/AuthProvider';
import { LoadingScreen } from '@/src/components/LoadingScreen';
import { colors } from '@/src/theme';

function TabIcon({ color, name }: { color: import('react-native').ColorValue; name: import('expo-symbols').SymbolViewProps['name'] }) {
  return <SymbolView name={name} tintColor={color} size={22} />;
}

export default function TabLayout() {
  const { user, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen />;
  if (!user) return <Redirect href="/login" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 64,
          paddingBottom: 7,
          paddingTop: 7,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '700' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => (
            <TabIcon
              color={color}
              name={{ ios: 'house.fill', android: 'home', web: 'home' }}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="opportunities"
        options={{
          title: 'Opportunities',
          tabBarIcon: ({ color }) => (
            <TabIcon color={color} name={{ ios: 'briefcase.fill', android: 'work', web: 'work' }} />
          ),
        }}
      />
      <Tabs.Screen
        name="discover"
        options={{
          title: 'Discover',
          tabBarIcon: ({ color }) => (
            <TabIcon
              color={color}
              name={{ ios: 'magnifyingglass', android: 'search', web: 'search' }}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="create"
        options={{
          title: 'Create',
          tabBarIcon: ({ color }) => (
            <TabIcon
              color={color}
              name={{ ios: 'plus.circle.fill', android: 'add_circle', web: 'add' }}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ color }) => (
            <TabIcon
              color={color}
              name={{ ios: 'bell.fill', android: 'notifications', web: 'notifications' }}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color }) => (
            <TabIcon
              color={color}
              name={{ ios: 'person.crop.circle.fill', android: 'account_circle', web: 'account_circle' }}
            />
          ),
        }}
      />
    </Tabs>
  );
}
