// The monthly spend ceiling, and who hears about it.

targetScope = 'resourceGroup'

@description('Environment discriminator — dev or prod.')
param env string

@description('Monthly ceiling in USD. Alerts fire at fractions of it, not at it.')
@minValue(1)
param monthlyLimitUsd int

@description('Where the alert goes. No default, and never written to a tracked file.')
param alertEmail string

@description('First day of the budget period, as YYYY-MM-01. Azure requires a start date and refuses one in the past.')
param startDate string

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'budget-charie-${env}'
  properties: {
    category: 'Cost'
    amount: monthlyLimitUsd
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
    }
    notifications: {
      // Three thresholds, and the first two are the useful ones.
      half: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [alertEmail]
        thresholdType: 'Actual'
      }
      most: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 90
        contactEmails: [alertEmail]
        thresholdType: 'Actual'
      }
      forecast: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [alertEmail]
        thresholdType: 'Forecasted'
      }
    }
  }
}

output id string = budget.id
