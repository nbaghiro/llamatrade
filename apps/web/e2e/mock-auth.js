// Script to inject mock auth state into localStorage
// Run this via Playwright's addInitScript before navigating

const mockAuthState = {
  state: {
    user: {
      id: 'test-user-id',
      email: 'test@llamatrade.dev',
      firstName: 'Test',
      lastName: 'User',
      roles: ['user'],
      tenantId: 'test-tenant',
    },
    accessToken: 'mock-access-token',
    refreshToken: 'mock-refresh-token',
    isAuthenticated: true,
  },
  version: 0,
};

localStorage.setItem('llamatrade-auth', JSON.stringify(mockAuthState));
