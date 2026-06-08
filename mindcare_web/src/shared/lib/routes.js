/**
 * Role-based routing constants.
 * Single source of truth for role → home URL mapping.
 */

export const ROLE_HOME = {
  student:      '/student',
  psychologist: '/psychologist',
  admin:        '/admin/users',
  supervisor:   '/supervisor',
};

/** Returns the home URL for a given role, defaulting to /profile. */
export const getRoleHome = (role) => ROLE_HOME[role] ?? '/profile';
