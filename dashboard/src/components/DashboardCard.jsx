import React from 'react';

const DashboardCard = ({ 
  title, 
  children, 
  className = '', 
  noPadding = false,
  actions = null 
}) => {
  return (
    <div className={`bg-white rounded-lg shadow-md ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-xl font-semibold text-gray-800">{title}</h2>
          {actions && <div>{actions}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-6'}>
        {children}
      </div>
    </div>
  );
};

export default DashboardCard; 