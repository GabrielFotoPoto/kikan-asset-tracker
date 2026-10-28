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

import { useState } from "react";

// Action destructive en deux temps : un premier clic arme le bouton, un second confirme.
export default function ConfirmButton({ children, confirmLabel = "Confirmer la suppression", onConfirm }) {
  const [armed, setArmed] = useState(false);
  if (!armed) return <button className="ghost" onClick={() => setArmed(true)}>{children}</button>;
  return (
    <span className="row">
      <button className="danger" onClick={() => { setArmed(false); onConfirm(); }}>{confirmLabel}</button>
      <button className="ghost" onClick={() => setArmed(false)}>Annuler</button>
    </span>
  );
}
