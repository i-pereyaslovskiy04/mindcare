export const ROLE_HOME = {
  student:      '/student',
  psychologist: '/psychologist',
  admin:        '/admin/users',
};

export const getRoleHome = (role) => ROLE_HOME[role] ?? '/';
