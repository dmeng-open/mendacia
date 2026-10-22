person(P) :- suspect(P).
person(P) :- victim(P).

{ at(P, L, T) : loc(L) } = 1 :- person(P), slot(T).

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

claim_holds(X) :- claim(X, _, P, S, O, T), true_stmt(P, S, O, T).

revealed(F) :- reveals(_, F).
revealed(F) :- pinned(F).
:- revealed(F), not holds(F).

#external crime_applies. [true]
{ culprit(S) : suspect(S) } = 1 :- crime_applies.
:- culprit(S), crime(L, T, _), not at(S, L, T).
:- culprit(S), crime(_, _, I), not has(S, I).
:- crime_applies, victim(V), crime(L, T, _), not at(V, L, T).

#show culprit/1.
