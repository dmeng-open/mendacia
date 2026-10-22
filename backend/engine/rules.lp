% Fixed rules for every case. compile_case appends the case as ground data only:
%   suspect/1 victim/1 loc/1 item/1 slot/1 crime/3
%   fact(F, Pred, Subj, Obj, Slot)   every case fact; Slot is none for has and owes
%   reveals(C, F)                    clue C pins fact F; dropped clues emit nothing
%   pinned(F)                        an extra fact, pinned like a revealed one
%   claim(Lie, Suspect, Pred, Subj, Obj, Slot)
% Open world: every world atom is a guess, and only clue pins rule worlds out.

person(P) :- suspect(P).
person(P) :- victim(P).

% Nobody is in two places in one slot.
{ at(P, L, T) : loc(L) } = 1 :- person(P), slot(T).

% has is not exclusive: an exclusive has lets one means clue name the culprit alone,
% which leaves every solution_chain clue redundant.
{ has(P, I) } :- person(P), item(I).

{ saw(A, B, T) } :- person(A), person(B), A != B, slot(T).
:- saw(A, B, T), at(A, L, T), not at(B, L, T).

{ heard(A, B, T) } :- person(A), person(B), A != B, slot(T).
{ owes(A, B) } :- person(A), person(B), A != B.

true_stmt(at, S, O, T) :- at(S, O, T).
true_stmt(has, S, O, none) :- has(S, O).
true_stmt(saw, S, O, T) :- saw(S, O, T).
true_stmt(heard, S, O, T) :- heard(S, O, T).
true_stmt(owes, S, O, none) :- owes(S, O).

holds(F) :- fact(F, P, S, O, T), true_stmt(P, S, O, T).

% A planned lie is testimony. It feeds claim_holds and never constrains a world.
claim_holds(X) :- claim(X, _, P, S, O, T), true_stmt(P, S, O, T).

revealed(F) :- reveals(_, F).
revealed(F) :- pinned(F).
:- revealed(F), not holds(F).

{ culprit(S) : suspect(S) } = 1.
:- culprit(S), crime(L, T, _), not at(S, L, T).
:- culprit(S), crime(_, _, I), not has(S, I).
:- victim(V), crime(L, T, _), not at(V, L, T).

#show culprit/1.
