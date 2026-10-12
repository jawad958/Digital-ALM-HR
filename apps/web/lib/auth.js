// NextAuth has been removed. This file stays as a shim so any leftover imports
// resolve without pulling in the retired package. For live auth state, use
// `auth` (localStorage-backed) from `@/lib/api`.
export const authOptions = {};
export const auth = async () => null;
export const handlers = {};
export const signIn = async () => {};
export const signOut = async () => {};
