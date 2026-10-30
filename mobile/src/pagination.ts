// Metadata stays outside JSON/array enumeration, preserving existing list code.
const continuation = Symbol('awinlink.next-page');
export function withNextPage<T>(items: T[], next: string | null): T[] {
  Object.defineProperty(items, continuation, { value: next, configurable: true });
  return items;
}
export function nextPage(items: readonly unknown[]): string | null {
  return (items as unknown as { [continuation]?: string | null })[continuation] ?? null;
}
export function preservePage<T>(source: readonly unknown[], items: T[]): T[] {
  return withNextPage(items, nextPage(source));
}
export function mergePage<T>(current: T[], incoming: T[]): T[] {
  const seen = new Set(current.map(item => (item as { id?: unknown })?.id).filter(id => id !== undefined));
  return withNextPage([...current, ...incoming.filter(item => {
    const id = (item as { id?: unknown })?.id;
    if (id === undefined) return true;
    if (seen.has(id)) return false;
    seen.add(id); return true;
  })], nextPage(incoming));
}

export function continuationPath(link: string | null, apiBase: string): string | null {
  if (!link) return null;
  const match = /<([^>]+)>;\s*rel="next"/.exec(link);
  if (!match) return null;
  const base = new URL(apiBase);
  const url = new URL(match[1], base);
  if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || url.username || url.password || url.hash) {
    throw new Error('Invalid pagination URL.');
  }
  return url.pathname.slice(base.pathname.length) + url.search;
}
