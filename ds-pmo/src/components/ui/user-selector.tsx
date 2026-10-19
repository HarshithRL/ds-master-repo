"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { X, Plus, Check, AlertCircle, UserPlus } from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";

export type SelectedUser = {
  id: string;
  name: string;
  email: string | null;
  emailVerified: Date | string | null;
  image?: string | null;
};

interface UserSelectorProps {
  mode: "single" | "multi";
  value: SelectedUser[];
  onChange: (users: SelectedUser[]) => void;
  placeholder?: string;
  requireEmail?: boolean;
  disabled?: boolean;
  className?: string;
}

function UserAvatar({ user, size = "sm" }: { user: SelectedUser; size?: "sm" | "md" }) {
  const isRegistered = !!user.emailVerified;
  const hasEmail = !!user.email;
  const dim = size === "md" ? "w-7 h-7" : "w-6 h-6";
  const text = size === "md" ? "text-[11px]" : "text-[10px]";

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full font-bold shrink-0",
        dim, text,
        isRegistered
          ? "bg-etex-orange text-white"
          : hasEmail
          ? "bg-orange-100 text-orange-700"
          : "bg-etex-gray-200 text-etex-gray-600"
      )}
    >
      {user.image ? (
        // No social OAuth providers yet, so user.image is never populated in
        // practice. Using next/image would require remotePatterns config for
        // hosts we don't have. Revisit when an avatar source is introduced.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={user.image} alt={user.name} className={cn(dim, "rounded-full object-cover")} />
      ) : (
        getInitials(user.name)
      )}
    </span>
  );
}

function StatusDot({ user }: { user: SelectedUser }) {
  const base = "text-[9px] font-semibold uppercase tracking-wide text-white rounded px-1.5 py-1 leading-none";
  if (user.emailVerified) {
    return <span className={cn(base, "bg-etex-orange")}>Member</span>;
  }
  if (user.email) {
    return <span className={cn(base, "bg-orange-400")}>Invited</span>;
  }
  return <span className={cn(base, "bg-etex-gray-400")}>External</span>;
}

type CreateMode = "register" | "external";

export function UserSelector({
  mode,
  value,
  onChange,
  placeholder,
  requireEmail = false,
  disabled = false,
  className,
}: UserSelectorProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<SelectedUser[]>([]);
  const [searching, setSearching] = useState(false);

  const [createMode, setCreateMode] = useState<CreateMode | null>(null);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [duplicateWarning, setDuplicateWarning] = useState<SelectedUser | null>(null);

  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchUsers = useCallback(async (q: string) => {
    setSearching(true);
    try {
      const data = await api.get<SelectedUser[]>(`/api/users?search=${encodeURIComponent(q)}`);
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    if (search.trim().length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    searchTimeout.current = setTimeout(() => fetchUsers(search), 200);
    return () => {
      if (searchTimeout.current) clearTimeout(searchTimeout.current);
    };
  }, [search, open, fetchUsers]);

  useEffect(() => {
    if (open) {
      setSearch("");
      setCreateMode(null);
      setNewName("");
      setNewEmail("");
      setCreateError("");
      setDuplicateWarning(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const isSelected = (id: string) => value.some((u) => u.id === id);

  const handleSelect = (user: SelectedUser) => {
    if (mode === "single") {
      onChange([user]);
      setOpen(false);
    } else {
      if (isSelected(user.id)) {
        onChange(value.filter((u) => u.id !== user.id));
      } else {
        onChange([...value, user]);
      }
    }
    setSearch("");
  };

  const handleRemove = (id: string) => {
    onChange(value.filter((u) => u.id !== id));
  };

  const handleCreateInit = (m: CreateMode) => {
    setCreateMode(m);
    setNewName(search);
    setNewEmail("");
    setCreateError("");
    setDuplicateWarning(null);
  };

  const handleCreate = async () => {
    if (!newName.trim()) {
      setCreateError("Name is required");
      return;
    }
    if (requireEmail || createMode === "register") {
      if (!newEmail.trim()) {
        setCreateError("Email is required");
        return;
      }
      if (!newEmail.endsWith("@etexgroup.com")) {
        setCreateError("Must be @etexgroup.com");
        return;
      }
    }

    const nameLower = newName.trim().toLowerCase();
    const nameMatch = results.find((r) => r.name.toLowerCase() === nameLower);
    if (nameMatch && !duplicateWarning) {
      setDuplicateWarning(nameMatch);
      return;
    }

    setCreating(true);
    setCreateError("");
    try {
      const payload: { name: string; email?: string } = { name: newName.trim() };
      if (createMode === "register" || requireEmail) {
        payload.email = newEmail.trim();
      }

      const created = await api.post<SelectedUser>("/api/users", payload);
      handleSelect(created);
      setCreateMode(null);
      setNewName("");
      setNewEmail("");
      setDuplicateWarning(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setCreateError("Email already exists — select them from the list.");
      } else {
        setCreateError("Failed to create. Try again.");
      }
    } finally {
      setCreating(false);
    }
  };

  const trimmedSearch = search.trim();
  const showAddOptions =
    !createMode &&
    trimmedSearch.length > 0 &&
    !results.some((r) => r.name.toLowerCase() === trimmedSearch.toLowerCase());

  const displayPlaceholder =
    placeholder ?? (mode === "single" ? "Select person…" : "Select people…");

  return (
    <div className={cn("w-full", className)}>
      {/* ── Selected users — stacked vertically ─────────────── */}
      {value.length > 0 && (
        <div className="flex flex-col gap-0.5 mb-1">
          {value.map((user) => (
            <div
              key={user.id}
              className="group flex items-center gap-2 px-1.5 py-1 rounded hover:bg-etex-gray-50 transition-colors"
            >
              <UserAvatar user={user} />
              <span className="text-sm text-etex-charcoal dark:text-gray-100 truncate flex-1">{user.name}</span>
              <StatusDot user={user} />
              {!disabled && (
                <button
                  type="button"
                  onClick={() => handleRemove(user.id)}
                  className="p-0.5 rounded hover:bg-etex-gray-200 text-etex-gray-300 hover:text-etex-gray-700 transition-colors"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Add button (inline plus) ────────────────────────── */}
      <Popover open={open} onOpenChange={disabled ? undefined : setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            className={cn(
              "flex items-center gap-1.5 px-1.5 py-1 rounded text-sm transition-all",
              "text-etex-gray-400 hover:text-etex-orange hover:bg-orange-50 dark:hover:bg-etex-orange/10/60 dark:hover:bg-etex-orange/10",
              "disabled:opacity-40 disabled:pointer-events-none",
              value.length === 0 && "text-etex-gray-400"
            )}
          >
            <Plus size={14} strokeWidth={2} />
            <span className="text-xs">{value.length === 0 ? displayPlaceholder : "Add"}</span>
          </button>
        </PopoverTrigger>

        <PopoverContent
          className="w-80 p-0 shadow-lg dark:shadow-[0_4px_12px_rgba(0,0,0,0.4)] border border-etex-gray-200 dark:border-(--border) rounded-md overflow-hidden"
          align="start"
        >
          {/* Search */}
          <div className="p-2 border-b border-etex-gray-100 dark:border-(--border)">
            <Input
              ref={inputRef}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCreateMode(null);
                setCreateError("");
                setDuplicateWarning(null);
              }}
              placeholder="Search by name or email…"
              className="h-8 text-xs"
            />
          </div>

          {/* Results */}
          {!createMode && (
            <div className="max-h-52 overflow-y-auto">
              {searching && (
                <div className="flex items-center gap-2 px-3 py-3">
                  <svg className="animate-spin h-3.5 w-3.5 text-etex-gray-400" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-xs text-etex-gray-400">Searching…</span>
                </div>
              )}
              {!searching && results.length === 0 && trimmedSearch.length >= 2 && (
                <p className="text-xs text-etex-gray-400 px-3 py-3">No results for &ldquo;{trimmedSearch}&rdquo;</p>
              )}
              {!searching && results.length === 0 && trimmedSearch.length < 2 && (
                <p className="text-xs text-etex-gray-400 px-3 py-3">Type at least 2 characters to search…</p>
              )}
              {results.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => handleSelect(user)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors",
                    isSelected(user.id)
                      ? "bg-orange-50/80 dark:bg-etex-orange/10"
                      : "hover:bg-etex-gray-50 dark:hover:bg-(--muted)"
                  )}
                >
                  <UserAvatar user={user} size="md" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-etex-charcoal dark:text-gray-100 truncate">{user.name}</p>
                    {user.email && (
                      <p className="text-[11px] text-etex-gray-400 truncate">{user.email}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusDot user={user} />
                    {isSelected(user.id) && <Check size={14} className="text-etex-orange" />}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Add-as options */}
          {showAddOptions && (
            <div className="border-t border-etex-gray-100 dark:border-(--border) p-1.5 flex flex-col gap-0.5">
              {!requireEmail && (
                <button
                  type="button"
                  onClick={() => handleCreateInit("external")}
                  className="flex items-center gap-2 w-full px-2 py-1.5 text-left text-sm text-etex-gray-600 hover:bg-etex-gray-50 rounded transition-colors"
                >
                  <UserPlus size={14} className="text-etex-gray-400" />
                  <span>Add <strong>&ldquo;{trimmedSearch}&rdquo;</strong> as external</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => handleCreateInit("register")}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-left text-sm text-etex-orange hover:bg-orange-50 dark:hover:bg-etex-orange/10 rounded transition-colors"
              >
                <UserPlus size={14} />
                <span>Register <strong>&ldquo;{trimmedSearch}&rdquo;</strong> with email</span>
              </button>
            </div>
          )}

          {/* requireEmail fallback */}
          {requireEmail && !createMode && !searching && trimmedSearch.length > 0 &&
            !results.some((r) => r.name.toLowerCase() === trimmedSearch.toLowerCase()) && (
            <div className="border-t border-etex-gray-100 dark:border-(--border) p-1.5">
              <button
                type="button"
                onClick={() => handleCreateInit("register")}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-left text-sm text-etex-orange hover:bg-orange-50 dark:hover:bg-etex-orange/10 rounded transition-colors"
              >
                <UserPlus size={14} />
                <span>Register <strong>&ldquo;{trimmedSearch}&rdquo;</strong>…</span>
              </button>
            </div>
          )}

          {/* Create form */}
          {createMode && (
            <div className="p-3 border-t border-etex-gray-100 dark:border-(--border) space-y-2">
              <p className="text-[11px] font-semibold text-etex-gray-600 uppercase tracking-wide">
                {createMode === "register" ? "Register new user" : "Add external person"}
              </p>

              <Input
                value={newName}
                onChange={(e) => { setNewName(e.target.value); setCreateError(""); setDuplicateWarning(null); }}
                placeholder="Full name"
                className="h-8 text-xs"
                autoFocus
              />

              {(createMode === "register" || requireEmail) && (
                <Input
                  value={newEmail}
                  onChange={(e) => { setNewEmail(e.target.value); setCreateError(""); }}
                  placeholder="email@etexgroup.com"
                  type="email"
                  className="h-8 text-xs"
                />
              )}

              {duplicateWarning && (
                <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded px-2 py-1.5">
                  <AlertCircle size={13} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-800 dark:text-amber-200">
                    <span className="font-semibold">{duplicateWarning.name}</span> already exists.
                    <button
                      type="button"
                      className="underline ml-1"
                      onClick={() => { handleSelect(duplicateWarning); setCreateMode(null); }}
                    >
                      Select them instead
                    </button>
                    {" or "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() => { setDuplicateWarning(null); handleCreate(); }}
                    >
                      create duplicate
                    </button>
                  </div>
                </div>
              )}

              {createError && (
                <p className="text-xs text-danger">{createError}</p>
              )}

              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={handleCreate}
                  disabled={creating}
                  className="bg-etex-orange hover:bg-etex-orange-dark text-white text-xs h-7 px-3"
                >
                  {creating ? "Adding…" : "Add"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => { setCreateMode(null); setCreateError(""); setDuplicateWarning(null); }}
                  className="text-xs h-7 px-3"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
