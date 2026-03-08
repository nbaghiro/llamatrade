#!/usr/bin/env npx ts-node
/* eslint-disable no-console */
/**
 * Template Validation Script
 *
 * Validates all strategy templates by parsing their S-expressions and running
 * comprehensive validation rules. Reports any issues found.
 *
 * Usage:
 *   npx ts-node scripts/validate-templates.ts
 *
 * Exit codes:
 *   0 - All templates valid
 *   1 - Some templates have errors
 */

import * as fs from 'fs';
import * as path from 'path';

// Import the parser and validator
import { fromDSLString, validateTree } from '../src/services/strategy-serializer';
import { validateStrategy } from '../src/services/validation';

interface TemplateIssue {
  templateId: string;
  templateName: string;
  type: 'parse_error' | 'validation_error' | 'validation_warning';
  message: string;
  blockId?: string;
}

interface TemplateData {
  id: string;
  name: string;
  config_sexpr: string;
}

// Read templates from Python file
function extractTemplatesFromPython(filePath: string): TemplateData[] {
  const content = fs.readFileSync(filePath, 'utf-8');
  const templates: TemplateData[] = [];

  // Match template definitions
  const templateRegex = /"([^"]+)":\s*\{[^}]*"id":\s*"([^"]+)"[^}]*"name":\s*"([^"]+)"[^}]*"config_sexpr":\s*"""([\s\S]*?)"""/g;

  let match;
  while ((match = templateRegex.exec(content)) !== null) {
    templates.push({
      id: match[2],
      name: match[3],
      config_sexpr: match[4],
    });
  }

  return templates;
}

// Validate a single template
function validateTemplate(template: TemplateData): TemplateIssue[] {
  const issues: TemplateIssue[] = [];

  // Try to parse the S-expression
  const parsed = fromDSLString(template.config_sexpr);

  if (!parsed) {
    issues.push({
      templateId: template.id,
      templateName: template.name,
      type: 'parse_error',
      message: 'Failed to parse S-expression',
    });
    return issues;
  }

  // Run structural validation (root block, parent references)
  const structuralResult = validateTree(parsed.tree);
  for (const error of structuralResult.errors) {
    issues.push({
      templateId: template.id,
      templateName: template.name,
      type: 'validation_error',
      message: error.message,
      blockId: error.blockId,
    });
  }

  // Run content validation (block rules, required fields)
  const result = validateStrategy(parsed.tree);

  for (const error of result.errors) {
    // Avoid duplicates from structural validation
    if (!issues.some(i => i.message === error.message)) {
      issues.push({
        templateId: template.id,
        templateName: template.name,
        type: 'validation_error',
        message: error.message,
        blockId: error.blockId,
      });
    }
  }

  for (const warning of result.warnings) {
    issues.push({
      templateId: template.id,
      templateName: template.name,
      type: 'validation_warning',
      message: warning.message,
      blockId: warning.blockId,
    });
  }

  return issues;
}

// Main execution
function main(): void {
  const templateServicePath = path.resolve(
    __dirname,
    '../../../services/strategy/src/services/template_service.py'
  );

  if (!fs.existsSync(templateServicePath)) {
    console.error(`Template service file not found: ${templateServicePath}`);
    process.exit(1);
  }

  console.log('🔍 Extracting templates from template_service.py...\n');

  const templates = extractTemplatesFromPython(templateServicePath);
  console.log(`Found ${templates.length} templates\n`);

  if (templates.length === 0) {
    console.error('No templates found! Check the regex pattern.');
    process.exit(1);
  }

  const allIssues: TemplateIssue[] = [];
  let passedCount = 0;
  let errorCount = 0;
  let warningCount = 0;

  for (const template of templates) {
    const issues = validateTemplate(template);
    const errors = issues.filter(i => i.type !== 'validation_warning');
    const warnings = issues.filter(i => i.type === 'validation_warning');

    if (errors.length === 0) {
      passedCount++;
      if (warnings.length > 0) {
        console.log(`⚠️  ${template.id}: Passed with ${warnings.length} warning(s)`);
        warningCount += warnings.length;
      } else {
        console.log(`✅ ${template.id}: Valid`);
      }
    } else {
      errorCount += errors.length;
      warningCount += warnings.length;
      console.log(`❌ ${template.id}: ${errors.length} error(s), ${warnings.length} warning(s)`);
      for (const error of errors) {
        console.log(`   ERROR: ${error.message}`);
      }
    }

    allIssues.push(...issues);
  }

  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY');
  console.log('='.repeat(60));
  console.log(`Total templates: ${templates.length}`);
  console.log(`Passed: ${passedCount}`);
  console.log(`Failed: ${templates.length - passedCount}`);
  console.log(`Total errors: ${errorCount}`);
  console.log(`Total warnings: ${warningCount}`);

  if (errorCount > 0) {
    console.log('\n❌ Some templates have validation errors\n');

    // Group issues by template
    const byTemplate = new Map<string, TemplateIssue[]>();
    for (const issue of allIssues.filter(i => i.type !== 'validation_warning')) {
      const existing = byTemplate.get(issue.templateId) || [];
      existing.push(issue);
      byTemplate.set(issue.templateId, existing);
    }

    console.log('DETAILED ERRORS:');
    console.log('-'.repeat(60));
    for (const [templateId, issues] of byTemplate) {
      const template = templates.find(t => t.id === templateId);
      console.log(`\n${templateId} ("${template?.name}"):`);
      for (const issue of issues) {
        console.log(`  - ${issue.type}: ${issue.message}`);
        if (issue.blockId) {
          console.log(`    Block: ${issue.blockId}`);
        }
      }
    }

    process.exit(1);
  }

  console.log('\n✅ All templates are valid!\n');
  process.exit(0);
}

main();
