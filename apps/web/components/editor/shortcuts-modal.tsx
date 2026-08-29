"use client";

import { X } from "lucide-react";

const shortcuts = [
  ["Play / pause", "Space"], ["Undo", "⌘/Ctrl Z"], ["Redo", "⌘/Ctrl ⇧ Z"], ["Delete notes", "Delete"],
  ["Move selected", "Arrow keys"], ["Copy / paste", "⌘/Ctrl C / V"], ["Duplicate", "⌘/Ctrl D"], ["Toggle loop", "L"], ["Toggle click", "M"], ["Zoom", "+ / −"],
];

export function ShortcutsModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
        <header className="modal-header"><div><h2 id="shortcut-title">Keyboard shortcuts</h2><p>Move quickly without taking your hands off the kit—or keyboard.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close shortcuts"><X /></button></header>
        <div className="shortcut-list">{shortcuts.map(([label, keys]) => <div key={label}><span>{label}</span><kbd>{keys}</kbd></div>)}</div>
      </section>
    </div>
  );
}
