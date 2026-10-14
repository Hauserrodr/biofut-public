import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import logo from '../assets/bdsm-logo.svg';

// Icons (you'll need to install @mui/icons-material if you want to use Material UI icons)
// For now, we'll use simple text

const Layout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const location = useLocation();
  
  const navigation = [
    { name: 'Dashboard', href: '/' },
    { name: 'Player Stats', href: '/players' },
    { name: 'Team Analysis', href: '/teams' },
    { name: 'Performance', href: '/performance' },
    { name: 'Rankings', href: '/rankings' },
    { name: 'Settings', href: '/settings' },
  ];

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-primary-main shadow-md">
        <div className="container mx-auto px-4 py-2 flex items-center">
          <button 
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-white mr-4 p-2 rounded-md hover:bg-primary-dark"
          >
            ☰
          </button>
          <div className="flex items-center">
            <img src={logo} alt="BDSM Logo" className="h-16 mr-3" />
            <h1 className="text-xl font-bold text-white leading-tight">
              B.D.S.M.<br />
              <span className="text-lg font-medium">BioFut Department of Statistical Magic</span>
            </h1>
          </div>
          <div className="text-white ml-auto">
            {/* User menu can go here */}
            <span>User Menu</span>
          </div>
        </div>
      </header>

      {/* Main Content Area with Sidebar */}
      <div className="container mx-auto px-4 py-6 flex">
        {/* Sidebar */}
        {sidebarOpen && (
          <aside className="w-64 mr-6">
            <nav className="bg-white rounded-lg shadow-md p-4">
              <ul className="space-y-2">
                {navigation.map((item) => (
                  <li key={item.name}>
                    <Link
                      to={item.href}
                      className={`block px-4 py-2 rounded-md ${
                        location.pathname === item.href
                          ? 'bg-primary-light text-white'
                          : 'text-gray-700 hover:bg-gray-100'
                      }`}
                    >
                      {item.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>
        )}

        {/* Main Content */}
        <main className={`flex-1 ${sidebarOpen ? '' : 'w-full'}`}>
          {children}
        </main>
      </div>

      {/* Footer */}
      <footer className="bg-gray-800 text-white py-4 mt-auto">
        <div className="container mx-auto px-4">
          <p className="text-center text-sm">
            BIOFUT Analytics Dashboard &copy; {new Date().getFullYear()}
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Layout; 