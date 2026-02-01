'use client';

import React from 'react';
import { Tile, Tag, SkeletonText } from '@carbon/react';
import { WarningAlt, Inventory } from '@carbon/icons-react';

interface AlertItem {
  part_number: string;
  part_name: string;
  category: string;
  quantity_on_hand: number;
  minimum_quantity: number;
  shortage: number;
}

interface InventoryAlertProps {
  title: string;
  alerts: AlertItem[];
  isLoading?: boolean;
  maxItems?: number;
}

export default function InventoryAlert({
  title,
  alerts,
  isLoading = false,
  maxItems = 5,
}: InventoryAlertProps) {
  if (isLoading) {
    return (
      <Tile className="p-4">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <SkeletonText paragraph lineCount={4} />
      </Tile>
    );
  }

  const displayAlerts = alerts.slice(0, maxItems);

  return (
    <Tile className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <WarningAlt className="text-yellow-500" />
          {title}
        </h3>
        {alerts.length > 0 && (
          <Tag type="red" size="sm">{alerts.length} 項</Tag>
        )}
      </div>
      
      {displayAlerts.length === 0 ? (
        <div className="text-center py-6 text-gray-500">
          <Inventory size={32} className="mx-auto mb-2 text-green-500" />
          <p>庫存充足，無警示項目</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {displayAlerts.map((alert) => (
            <li
              key={alert.part_number}
              className="flex items-center justify-between p-2 bg-red-50 rounded-lg border-l-4 border-red-500"
            >
              <div>
                <p className="font-medium text-sm">{alert.part_name}</p>
                <p className="text-xs text-gray-500">
                  {alert.part_number} · {alert.category}
                </p>
              </div>
              <div className="text-right">
                <p className="font-bold text-red-600">
                  {alert.quantity_on_hand} / {alert.minimum_quantity}
                </p>
                <p className="text-xs text-gray-500">
                  缺 {alert.shortage} 件
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      
      {alerts.length > maxItems && (
        <p className="text-sm text-gray-500 mt-3 text-center">
          還有 {alerts.length - maxItems} 項警示...
        </p>
      )}
    </Tile>
  );
}
