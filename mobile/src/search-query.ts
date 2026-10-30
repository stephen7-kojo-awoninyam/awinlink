import { useEffect, useState } from 'react';

export function searchPath(base: string, query: string) {
  const term = query.trim().replace(/^@/, '');
  return term ? `${base}?search=${encodeURIComponent(term)}` : base;
}

export function useSearchPath(base: string, query: string) {
  const path = searchPath(base, query);
  const [settled, setSettled] = useState(path);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(path), 250);
    return () => clearTimeout(timer);
  }, [path]);
  // A role/directory switch must not request the previous endpoint while waiting.
  return settled.split('?')[0] === base ? settled : base;
}
