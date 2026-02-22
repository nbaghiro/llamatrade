export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-slate-400 mt-1">Manage your account and preferences</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alpaca API Keys */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Alpaca API Keys</h2>
          <div className="space-y-4">
            <div>
              <label className="label">Paper Trading API Key</label>
              <input type="password" className="input" placeholder="Enter API key" />
            </div>
            <div>
              <label className="label">Paper Trading Secret</label>
              <input type="password" className="input" placeholder="Enter secret" />
            </div>
            <button className="btn btn-primary">Save Keys</button>
          </div>
        </div>

        {/* Notifications */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Notifications</h2>
          <div className="space-y-4">
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4 rounded border-slate-600 bg-slate-800" />
              <span className="text-slate-300">Email notifications</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4 rounded border-slate-600 bg-slate-800" />
              <span className="text-slate-300">Trade alerts</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4 rounded border-slate-600 bg-slate-800" />
              <span className="text-slate-300">Daily summary</span>
            </label>
          </div>
        </div>

        {/* Subscription */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Subscription</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white font-medium">Free Plan</p>
              <p className="text-slate-400 text-sm">5 backtests/month, paper trading only</p>
            </div>
            <button className="btn btn-secondary">Upgrade</button>
          </div>
        </div>

        {/* Account */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Account</h2>
          <div className="space-y-4">
            <div>
              <label className="label">Email</label>
              <input type="email" className="input" value="user@example.com" disabled />
            </div>
            <button className="btn btn-secondary">Change Password</button>
          </div>
        </div>
      </div>
    </div>
  );
}
