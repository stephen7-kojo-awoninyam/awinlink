export type Participant = { id: number; user: number; display_name: string; role: string; admission_state: string };
export type Session = { id: number; title: string; status: string; scheduled_start?: string; my_participant: Participant | null; capabilities: Record<string, boolean> };
export type BoardObject = { id: string; kind: string; color: string; width: number; points?: number[][]; x?: number; y?: number; w?: number; h?: number; size?: number; text?: string };
export type Board = { session_id: number; revision: number; objects: Record<string, BoardObject>; editors: number[]; can_edit: boolean; can_manage: boolean };
export type ChatMessage = { id: number; client_id: string; sender_id: number; sender_name: string; text: string };
export type ClassroomState = { status: string; error: string; session: Session | null; participants: Participant[]; peers: { participant_id: number; user_id: number; role: string; generation: string }[]; localStream: any; remoteStreams: Record<number, any>; board: Board | null; chat: ChatMessage[]; connected: boolean; activityConnected: boolean; camera: boolean; microphone: boolean; sharing: boolean; busy: boolean; rosterPage: number; rosterHasNext: boolean; rosterHasPrevious: boolean };
export type ClassroomOptions = { sessionId: number; api: (path: string, method?: string, body?: unknown) => Promise<any>; socket: (path: string) => Promise<WebSocket>; media: (constraints: { audio: boolean; video: boolean }) => Promise<any>; canCapture?: () => boolean; display?: () => Promise<any>; peer: (ice: any[], policy: "all" | "relay") => any; validateIce: (value: unknown) => any[]; onState: (state: ClassroomState) => void };
export class ClassroomClient {
  constructor(options: ClassroomOptions);
  state: ClassroomState;
  load(): Promise<Session | undefined>;
  changeRosterPage(delta: number): Promise<void>;
  join(media?: { camera: boolean; microphone: boolean }): Promise<void>;
  leave(): Promise<void>;
  dispose(): Promise<void>;
  action(action: string, participantId?: number): Promise<void>;
  boardCommand(action: string, payload?: unknown): Promise<void>;
  chat(text: string): Promise<void>;
  toggle(kind: 'camera' | 'microphone'): Promise<void>;
  share(): Promise<void>;
}
export function uuid(): string;
export function point(x: number, y: number): number[];
export function objectAt(objects: Record<string, BoardObject>, x: number, y: number): string | undefined;
export function sampledPoints(points: number[][], maximum?: number): number[][];
