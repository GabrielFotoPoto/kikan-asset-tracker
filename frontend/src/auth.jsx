import { createContext, useContext } from "react";

export const AuthContext = createContext({ user: null });

export function useAuth() {
  return useContext(AuthContext);
}

// Droits d'ecriture par domaine, alignes sur le backend.
export function canWrite(role, domain) {
  if (domain === "users") return role === "rh" || role === "informatique";
  // entites, materiel, remises, import, applications : informatique
  return role === "informatique";
}
