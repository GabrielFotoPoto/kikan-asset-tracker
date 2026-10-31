/*
 * Kikan - suivi des actifs et remise de materiel signee
 * Copyright (C) 2026 Gabriel Chollet
 * Developpe avec l'assistance d'une IA (Claude, Anthropic).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// Les trois etats d'une liste : chargement, vide, erreur.

export function Loading({ label = "Chargement en cours" }) {
  return (
    <div role="status" aria-label={label} className="skeleton">
      <span className="skeleton-bar" /><span className="skeleton-bar w80" /><span className="skeleton-bar w60" />
    </div>
  );
}

export function Empty({ title, hint, children }) {
  return (
    <div className="state-empty">
      <strong>{title}</strong>
      {hint && <span className="muted">{hint}</span>}
      {children}
    </div>
  );
}

export function ErrorState({ title = "Impossible de charger les donnees", message, onRetry }) {
  return (
    <div role="alert" className="state-error">
      <strong>{title}</strong>
      {message && <span>{message}</span>}
      {onRetry && <div><button type="button" onClick={onRetry}>Reessayer</button></div>}
    </div>
  );
}
