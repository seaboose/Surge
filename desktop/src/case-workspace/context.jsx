import { useState, useEffect, useRef, createContext } from "react";

export const Context = createContext(null);

export async function request(method, args = {}) {
  const reply = await window.surge.request(method, args);
  if (!reply.ok) throw new Error(reply.error);
  return reply.value;
}

export function useData(method, args, enabled = true, refresh = 0) {
  const [result, setResult] = useState(null),
    [failure, setFailure] = useState(null);
  const key = JSON.stringify(args);
  const cache = useRef(null);
  useEffect(() => {
    let alive = true;
    if (
      enabled &&
      !(cache.current?.key === key && cache.current?.refresh === refresh)
    ) {
      setFailure(null);
      request(method, JSON.parse(key))
        .then((v) => {
          if (alive) {
            cache.current = { key, refresh };
            setResult({ key, refresh, value: v });
          }
        })
        .catch((e) => {
          if (alive) setFailure({ key, refresh, error: e.message });
        });
    }
    return () => {
      alive = false;
    };
  }, [method, key, enabled, refresh]);
  return [
    result?.key === key && result?.refresh === refresh ? result.value : null,
    failure?.key === key && failure?.refresh === refresh ? failure.error : "",
  ];
}

export function useDebounce(value) {
  const [result, set] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => set(value), 120);
    return () => clearTimeout(id);
  }, [value]);
  return result;
}
