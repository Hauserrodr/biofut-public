import React, { useState } from 'react';
import DashboardCard from '../components/DashboardCard';

const Settings = () => {
  const [dataSource, setDataSource] = useState('excel');
  const [darkMode, setDarkMode] = useState(false);
  const [notifications, setNotifications] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(5);
  
  const handleFileUpload = (e) => {
    // In a real app, this would handle file upload
    console.log('File selected:', e.target.files[0]);
    // You would process the file here
  };
  
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold mb-2">Settings</h1>
        <p className="text-gray-600">Configure your BIOFUT Analytics Dashboard</p>
      </div>
      
      <DashboardCard title="Data Source">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Select Data Source</label>
            <div className="mt-2 space-y-2">
              <div className="flex items-center">
                <input
                  id="excel"
                  name="dataSource"
                  type="radio"
                  className="h-4 w-4 text-primary-main border-gray-300"
                  checked={dataSource === 'excel'}
                  onChange={() => setDataSource('excel')}
                />
                <label htmlFor="excel" className="ml-3 block text-sm font-medium text-gray-700">
                  Excel File
                </label>
              </div>
              <div className="flex items-center">
                <input
                  id="api"
                  name="dataSource"
                  type="radio"
                  className="h-4 w-4 text-primary-main border-gray-300"
                  checked={dataSource === 'api'}
                  onChange={() => setDataSource('api')}
                />
                <label htmlFor="api" className="ml-3 block text-sm font-medium text-gray-700">
                  API Connection
                </label>
              </div>
              <div className="flex items-center">
                <input
                  id="database"
                  name="dataSource"
                  type="radio"
                  className="h-4 w-4 text-primary-main border-gray-300"
                  checked={dataSource === 'database'}
                  onChange={() => setDataSource('database')}
                />
                <label htmlFor="database" className="ml-3 block text-sm font-medium text-gray-700">
                  Database Connection
                </label>
              </div>
            </div>
          </div>
          
          {dataSource === 'excel' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Upload Excel File</label>
              <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md">
                <div className="space-y-1 text-center">
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    stroke="currentColor"
                    fill="none"
                    viewBox="0 0 48 48"
                    aria-hidden="true"
                  >
                    <path
                      d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <div className="flex text-sm text-gray-600">
                    <label
                      htmlFor="file-upload"
                      className="relative cursor-pointer bg-white rounded-md font-medium text-primary-main hover:text-primary-dark"
                    >
                      <span>Upload a file</span>
                      <input id="file-upload" name="file-upload" type="file" className="sr-only" onChange={handleFileUpload} />
                    </label>
                    <p className="pl-1">or drag and drop</p>
                  </div>
                  <p className="text-xs text-gray-500">Excel files only (XLSX)</p>
                </div>
              </div>
            </div>
          )}
          
          {dataSource === 'api' && (
            <div>
              <label htmlFor="api-url" className="block text-sm font-medium text-gray-700 mb-2">
                API URL
              </label>
              <input
                type="text"
                name="api-url"
                id="api-url"
                className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                placeholder="https://api.example.com/biofut"
              />
              <p className="mt-2 text-sm text-gray-500">
                Enter the URL of the BIOFUT API endpoint
              </p>
            </div>
          )}
          
          {dataSource === 'database' && (
            <div className="space-y-4">
              <div>
                <label htmlFor="db-host" className="block text-sm font-medium text-gray-700 mb-2">
                  Database Host
                </label>
                <input
                  type="text"
                  name="db-host"
                  id="db-host"
                  className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                  placeholder="localhost"
                />
              </div>
              <div>
                <label htmlFor="db-name" className="block text-sm font-medium text-gray-700 mb-2">
                  Database Name
                </label>
                <input
                  type="text"
                  name="db-name"
                  id="db-name"
                  className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                  placeholder="biofut_db"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="db-user" className="block text-sm font-medium text-gray-700 mb-2">
                    Username
                  </label>
                  <input
                    type="text"
                    name="db-user"
                    id="db-user"
                    className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                    placeholder="username"
                  />
                </div>
                <div>
                  <label htmlFor="db-password" className="block text-sm font-medium text-gray-700 mb-2">
                    Password
                  </label>
                  <input
                    type="password"
                    name="db-password"
                    id="db-password"
                    className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                    placeholder="••••••••"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </DashboardCard>
      
      <DashboardCard title="Display Settings">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-medium text-gray-900">Dark Mode</h3>
              <p className="text-sm text-gray-500">Enable dark mode for the dashboard</p>
            </div>
            <button
              type="button"
              className={`${
                darkMode ? 'bg-primary-main' : 'bg-gray-200'
              } relative inline-flex flex-shrink-0 h-6 w-11 border-2 border-transparent rounded-full cursor-pointer transition-colors ease-in-out duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-main`}
              onClick={() => setDarkMode(!darkMode)}
            >
              <span className="sr-only">Use dark mode</span>
              <span
                className={`${
                  darkMode ? 'translate-x-5' : 'translate-x-0'
                } pointer-events-none relative inline-block h-5 w-5 rounded-full bg-white shadow transform ring-0 transition ease-in-out duration-200`}
              >
                <span
                  className={`${
                    darkMode ? 'opacity-0 ease-out duration-100' : 'opacity-100 ease-in duration-200'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-gray-400" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M4 8l2-2m0 0l2-2M6 6L4 4m2 2l2 2" />
                  </svg>
                </span>
                <span
                  className={`${
                    darkMode ? 'opacity-100 ease-in duration-200' : 'opacity-0 ease-out duration-100'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-primary-main" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M3.707 5.293a1 1 0 00-1.414 1.414l1.414-1.414zM5 8l-.707.707a1 1 0 001.414 0L5 8zm4.707-3.293a1 1 0 00-1.414-1.414l1.414 1.414zm-7.414 2l2 2 1.414-1.414-2-2-1.414 1.414zm3.414 2l4-4-1.414-1.414-4 4 1.414 1.414z" />
                  </svg>
                </span>
              </span>
            </button>
          </div>
          
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-medium text-gray-900">Notifications</h3>
              <p className="text-sm text-gray-500">Receive notifications about updates</p>
            </div>
            <button
              type="button"
              className={`${
                notifications ? 'bg-primary-main' : 'bg-gray-200'
              } relative inline-flex flex-shrink-0 h-6 w-11 border-2 border-transparent rounded-full cursor-pointer transition-colors ease-in-out duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-main`}
              onClick={() => setNotifications(!notifications)}
            >
              <span className="sr-only">Enable notifications</span>
              <span
                className={`${
                  notifications ? 'translate-x-5' : 'translate-x-0'
                } pointer-events-none relative inline-block h-5 w-5 rounded-full bg-white shadow transform ring-0 transition ease-in-out duration-200`}
              >
                <span
                  className={`${
                    notifications ? 'opacity-0 ease-out duration-100' : 'opacity-100 ease-in duration-200'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-gray-400" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M4 8l2-2m0 0l2-2M6 6L4 4m2 2l2 2" />
                  </svg>
                </span>
                <span
                  className={`${
                    notifications ? 'opacity-100 ease-in duration-200' : 'opacity-0 ease-out duration-100'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-primary-main" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M3.707 5.293a1 1 0 00-1.414 1.414l1.414-1.414zM5 8l-.707.707a1 1 0 001.414 0L5 8zm4.707-3.293a1 1 0 00-1.414-1.414l1.414 1.414zm-7.414 2l2 2 1.414-1.414-2-2-1.414 1.414zm3.414 2l4-4-1.414-1.414-4 4 1.414 1.414z" />
                  </svg>
                </span>
              </span>
            </button>
          </div>
          
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-medium text-gray-900">Auto Refresh</h3>
              <p className="text-sm text-gray-500">Automatically refresh data</p>
            </div>
            <button
              type="button"
              className={`${
                autoRefresh ? 'bg-primary-main' : 'bg-gray-200'
              } relative inline-flex flex-shrink-0 h-6 w-11 border-2 border-transparent rounded-full cursor-pointer transition-colors ease-in-out duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-main`}
              onClick={() => setAutoRefresh(!autoRefresh)}
            >
              <span className="sr-only">Enable auto refresh</span>
              <span
                className={`${
                  autoRefresh ? 'translate-x-5' : 'translate-x-0'
                } pointer-events-none relative inline-block h-5 w-5 rounded-full bg-white shadow transform ring-0 transition ease-in-out duration-200`}
              >
                <span
                  className={`${
                    autoRefresh ? 'opacity-0 ease-out duration-100' : 'opacity-100 ease-in duration-200'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-gray-400" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M4 8l2-2m0 0l2-2M6 6L4 4m2 2l2 2" />
                  </svg>
                </span>
                <span
                  className={`${
                    autoRefresh ? 'opacity-100 ease-in duration-200' : 'opacity-0 ease-out duration-100'
                  } absolute inset-0 h-full w-full flex items-center justify-center transition-opacity`}
                  aria-hidden="true"
                >
                  <svg className="h-3 w-3 text-primary-main" fill="currentColor" viewBox="0 0 12 12">
                    <path d="M3.707 5.293a1 1 0 00-1.414 1.414l1.414-1.414zM5 8l-.707.707a1 1 0 001.414 0L5 8zm4.707-3.293a1 1 0 00-1.414-1.414l1.414 1.414zm-7.414 2l2 2 1.414-1.414-2-2-1.414 1.414zm3.414 2l4-4-1.414-1.414-4 4 1.414 1.414z" />
                  </svg>
                </span>
              </span>
            </button>
          </div>
          
          {autoRefresh && (
            <div>
              <label htmlFor="refresh-interval" className="block text-sm font-medium text-gray-700 mb-2">
                Refresh Interval (minutes)
              </label>
              <input
                type="number"
                name="refresh-interval"
                id="refresh-interval"
                min="1"
                max="60"
                className="shadow-sm focus:ring-primary-main focus:border-primary-main block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(parseInt(e.target.value))}
              />
            </div>
          )}
        </div>
      </DashboardCard>
      
      <div className="flex justify-end">
        <button
          type="button"
          className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-main"
        >
          Cancel
        </button>
        <button
          type="button"
          className="ml-3 inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-main hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-main"
        >
          Save Settings
        </button>
      </div>
    </div>
  );
};

export default Settings; 