export const ROLE_HOME = {
  student:      '/student',
  psychologist: '/psychologist',
  admin:        '/admin',
};

export const getRoleHome = (role) => ROLE_HOME[role] ?? '/';
