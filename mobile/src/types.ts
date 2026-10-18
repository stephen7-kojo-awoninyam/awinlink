export type User = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: 'ATHLETE' | 'ORGANIZATION' | 'SCOUT' | 'COACH' | 'ADMIN' | string;
  profile_picture: string | null;
  country: string | null;
};

export type AuthResponse = {
  user: User;
  access: string;
  refresh: string;
};

export type RegistrationData = {
  first_name: string;
  last_name: string;
  username: string;
  email: string;
  phone_number: string;
  country: string;
  role: 'ATHLETE' | 'ORGANIZATION' | 'SCOUT' | 'COACH';
  password1: string;
  password2: string;
  organization_name?: string;
  organization_username?: string;
  organization_email?: string;
  website?: string;
};

export type FeedPost = {
  author: number;
  id: number;
  author_name: string;
  author_username: string;
  author_profile_picture: string | null;
  caption: string;
  image: string | null;
  video: string | null;
  post_type: string;
  location: string;
  likes_count: number;
  comments_count: number;
  is_liked: boolean;
  created_at: string;
};

export type TalentProfile = {
  id: number;
  user: User;
  headline?: string;
  talent_area?: string;
  talent_category?: string;
  biography?: string;
  country?: string;
  city?: string;
  profile_photo?: string | null;
  followers_count?: number;
  following_count?: number;
  skills?: string[];
  domains?: string[];
};

export type Connection = {
  id: number;
  sender_id: number;
  receiver_id: number;
  status: string;
};

export type MessagingUser = Pick<
  User,
  'id' | 'username' | 'first_name' | 'last_name' | 'profile_picture'
>;

export type Message = {
  id: number;
  conversation: number;
  sender: MessagingUser;
  message_type: string;
  content: string;
  image: string | null;
  video: string | null;
  file: string | null;
  audio: string | null;
  created_at: string;
  is_read: boolean;
};

export type Conversation = {
  unread_count?: number;
  id: number;
  opportunity: number | null;
  is_group: boolean;
  name: string | null;
  participants: { id: number; user: MessagingUser }[];
  last_message: Message | null;
  updated_at: string;
};

export type AppNotification = {
  post_id?: number | null;
  conversation_id?: number | null;
  opportunity_id?: number | null;
  id: number;
  message: string;
  notification_type_display: string;
  sender_name: string | null;
  sender_username: string | null;
  is_read: boolean;
  created_at: string;
};
