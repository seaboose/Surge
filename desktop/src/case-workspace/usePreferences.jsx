import { useEffect, useState } from "react";
import {
  DEFAULT_PREFERENCES,
  PREFERENCE_KEY,
  parsePreferences,
} from "./preferences.mjs";

function initialPreferences() {
  try {
    return {
      value: parsePreferences(localStorage.getItem(PREFERENCE_KEY)),
      error: "",
    };
  } catch {
    return {
      value: { ...DEFAULT_PREFERENCES },
      error: "Saved settings could not be read. Defaults are in use.",
    };
  }
}

export default function usePreferences() {
  const [stored, setStored] = useState(initialPreferences);
  const [systemMotion, setSystemMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const reducedMotion = stored.value.reduceMotion ?? systemMotion;
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => setSystemMotion(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(reducedMotion);
  }, [reducedMotion]);
  function update(patch) {
    const value = { ...stored.value, ...patch };
    let error = "";
    try {
      localStorage.setItem(PREFERENCE_KEY, JSON.stringify(value));
    } catch {
      error = "Settings apply for this session but could not be saved.";
    }
    setStored({ value, error });
  }
  return {
    preferences: stored.value,
    error: stored.error,
    reducedMotion,
    update,
  };
}
