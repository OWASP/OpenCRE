"""
Standard-specific handlers for different compliance frameworks.
These handlers process various standard formats and convert them to a common format.
"""

import csv
import json
import logging
import re
import io
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, BinaryIO, TextIO, Union

# Set up logging
logger = logging.getLogger(__name__)

class StandardSpecificHandler:
    """
    Handles parsing and processing of specific standards with unique structures.
    This class contains static methods for each supported standard.
    """
    
    @staticmethod
    def detect_standard_type(file_content: Union[str, bytes], filename: str = None) -> str:
        """
        Detect the standard type from file content and name.
        
        Args:
            file_content: File content as string or bytes
            filename: Optional filename with extension
            
        Returns:
            Standard type identifier (pci_dss, soc2, dora, etc.)
        """
        content_sample = file_content[:4096].lower() if isinstance(file_content, str) else file_content[:4096].decode('utf-8', errors='ignore').lower()
        
        # Check filename extension
        if filename:
            if filename.lower().endswith('.csv'):
                # CSV file - check content patterns
                if 'pci' in content_sample and ('dss' in content_sample or 'requirement' in content_sample):
                    return 'pci_dss'
                elif 'soc' in content_sample and ('trust service' in content_sample or 'criteria' in content_sample):
                    return 'soc2'
                elif 'dora' in content_sample:
                    return 'dora'
            elif filename.lower().endswith('.json'):
                if 'owasp' in content_sample and ('ai' in content_sample or 'llm' in content_sample):
                    return 'owasp_ai'
                    
        # Check content patterns
        if 'pci dss' in content_sample or 'payment card industry' in content_sample:
            return 'pci_dss'
        elif 'soc 2' in content_sample or 'trust service criteria' in content_sample:
            return 'soc2'
        elif 'dora' in content_sample or 'digital operational resilience act' in content_sample:
            return 'dora'
        elif 'owasp' in content_sample and ('ai' in content_sample or 'llm' in content_sample):
            return 'owasp_ai'
            
        # Default to generic standard
        return 'generic'
    
    @staticmethod
    def process_standard_file(file_data: Union[BinaryIO, TextIO, str, bytes], 
                             standard_type: Optional[str] = None) -> List[Dict]:
        """
        Process standard file into common control format.
        
        Args:
            file_data: File-like object or content
            standard_type: Type of standard, auto-detected if not specified
            
        Returns:
            List of controls in standard format
        """
        # Convert string/bytes to file-like object if needed
        if isinstance(file_data, (str, bytes)):
            content = file_data
            filename = None
            
            # Create file-like object
            if isinstance(content, str):
                file_data = io.StringIO(content)
            else:
                file_data = io.BytesIO(content)
                
            # Auto-detect standard type if not specified
            if not standard_type:
                standard_type = StandardSpecificHandler.detect_standard_type(content, filename)
        else:
            # Get standard type if not specified
            if not standard_type:
                # Read a sample of the file
                position = file_data.tell()
                content_sample = file_data.read(4096)
                file_data.seek(position)  # Reset position
                
                # Get filename if possible
                filename = getattr(file_data, 'name', None)
                
                # Detect standard type
                standard_type = StandardSpecificHandler.detect_standard_type(content_sample, filename)
        
        # Process according to standard type
        if standard_type == 'pci_dss':
            return StandardSpecificHandler.process_pci_dss(file_data)
        elif standard_type == 'soc2':
            return StandardSpecificHandler.process_soc2(file_data)
        elif standard_type == 'dora':
            return StandardSpecificHandler.process_dora(file_data)
        elif standard_type == 'owasp_ai':
            return StandardSpecificHandler.process_owasp_ai(file_data)
        else:
            # Try to process as generic CSV or JSON
            try:
                return StandardSpecificHandler.process_generic(file_data)
            except Exception as e:
                logger.error(f"Failed to process standard file: {e}")
                return []
    
    @staticmethod
    def process_pci_dss(file_data) -> List[Dict]:
        """
        Process PCI-DSS standard with its specific format.
        
        Args:
            file_data: File-like object with PCI DSS content
            
        Returns:
            List of controls in standard format
        """
        controls = []
        
        try:
            # Check if file_data is CSV
            if hasattr(file_data, 'read'):
                # Reset position
                file_data.seek(0)
                
                # Read as CSV
                reader = csv.reader(file_data)
                headers = next(reader, None)
                
                # Find relevant column indices
                req_col = -1
                desc_col = -1
                
                for i, header in enumerate(headers or []):
                    header_lower = header.lower()
                    if 'requirement' in header_lower or 'control' in header_lower:
                        req_col = i
                    elif 'description' in header_lower or 'text' in header_lower:
                        desc_col = i
                
                if req_col == -1 or desc_col == -1:
                    # Try to guess columns if headers not identified
                    req_col, desc_col = 0, 1
                
                # Parse rows
                for row in reader:
                    if len(row) <= max(req_col, desc_col):
                        continue  # Skip rows with insufficient columns
                    
                    requirement = row[req_col].strip()
                    description = row[desc_col].strip()
                    
                    if requirement and description:
                        # Extract and format requirement ID
                        req_id = StandardSpecificHandler._extract_pci_dss_id(requirement)
                        if not req_id:
                            req_id = requirement
                        
                        controls.append({
                            "id": req_id,
                            "name": f"PCI DSS {req_id}",
                            "description": description,
                            "standard": "PCI DSS",
                            "section": StandardSpecificHandler._extract_pci_section(req_id)
                        })
            else:
                # Treat as string content
                content = file_data
                
                # Simple regex-based parsing
                requirement_pattern = r'(?:Requirement|Control)\s+(\d+(?:\.\d+)*)\s*[:\.]\s*([^\n]+)'
                matches = re.finditer(requirement_pattern, content, re.IGNORECASE)
                
                for match in matches:
                    req_id = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if req_id and description:
                        controls.append({
                            "id": req_id,
                            "name": f"PCI DSS {req_id}",
                            "description": description,
                            "standard": "PCI DSS",
                            "section": StandardSpecificHandler._extract_pci_section(req_id)
                        })
        
        except Exception as e:
            logger.error(f"Error processing PCI DSS file: {e}")
            
        return controls
    
    @staticmethod
    def _extract_pci_dss_id(text: str) -> str:
        """Extract PCI DSS ID from text."""
        # Look for patterns like "Requirement 1.2.3" or "1.2.3"
        patterns = [
            r'Requirement\s+(\d+(?:\.\d+)*)',
            r'(\d+\.\d+(?:\.\d+)*)',
            r'Requirement\s+(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
                
        return ""
    
    @staticmethod
    def _extract_pci_section(req_id: str) -> str:
        """Extract PCI DSS section from requirement ID."""
        if not req_id:
            return ""
            
        parts = req_id.split('.')
        if len(parts) > 0:
            return parts[0]
        return ""
    
    @staticmethod
    def process_soc2(file_data) -> List[Dict]:
        """
        Process SOC2 with its specific structure.
        
        Args:
            file_data: File-like object with SOC2 content
            
        Returns:
            List of controls in standard format
        """
        controls = []
        
        try:
            # Check if file_data is CSV
            if hasattr(file_data, 'read'):
                # Reset position
                file_data.seek(0)
                
                # Read as CSV
                reader = csv.reader(file_data)
                headers = next(reader, None)
                
                # Find relevant column indices
                id_col, name_col, desc_col, category_col = -1, -1, -1, -1
                
                for i, header in enumerate(headers or []):
                    header_lower = header.lower()
                    if 'id' in header_lower or 'control' in header_lower:
                        id_col = i
                    elif 'name' in header_lower or 'title' in header_lower:
                        name_col = i
                    elif 'description' in header_lower or 'text' in header_lower:
                        desc_col = i
                    elif 'category' in header_lower or 'principle' in header_lower:
                        category_col = i
                
                if id_col == -1 or desc_col == -1:
                    # Try to guess columns if headers not identified
                    id_col, name_col, desc_col, category_col = 0, 1, 2, 3
                
                # Parse rows
                for row in reader:
                    if len(row) <= max(id_col, desc_col):
                        continue  # Skip rows with insufficient columns
                    
                    control_id = row[id_col].strip()
                    name = row[name_col].strip() if name_col >= 0 and name_col < len(row) else ""
                    description = row[desc_col].strip()
                    category = row[category_col].strip() if category_col >= 0 and category_col < len(row) else ""
                    
                    if control_id and description:
                        controls.append({
                            "id": control_id,
                            "name": name or f"SOC2 {control_id}",
                            "description": description,
                            "standard": "SOC2",
                            "section": category or StandardSpecificHandler._extract_soc2_category(control_id)
                        })
            else:
                # Treat as string content
                content = file_data
                
                # Simple regex-based parsing
                control_pattern = r'(CC\d+\.\d+)\s*[-:]\s*([^\n]+)'
                matches = re.finditer(control_pattern, content, re.IGNORECASE)
                
                for match in matches:
                    control_id = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if control_id and description:
                        controls.append({
                            "id": control_id,
                            "name": f"SOC2 {control_id}",
                            "description": description,
                            "standard": "SOC2",
                            "section": StandardSpecificHandler._extract_soc2_category(control_id)
                        })
        
        except Exception as e:
            logger.error(f"Error processing SOC2 file: {e}")
            
        return controls
    
    @staticmethod
    def _extract_soc2_category(control_id: str) -> str:
        """Extract SOC2 category from control ID."""
        # SOC2 categories: CC1.x = Control Environment, CC2.x = Communication, etc.
        categories = {
            "CC1": "Control Environment",
            "CC2": "Communication and Information",
            "CC3": "Risk Assessment",
            "CC4": "Monitoring Activities",
            "CC5": "Control Activities",
            "CC6": "Logical and Physical Access Controls",
            "CC7": "System Operations",
            "CC8": "Change Management",
            "CC9": "Risk Mitigation"
        }
        
        if not control_id:
            return ""
            
        prefix = control_id.split('.')[0] if '.' in control_id else control_id[:3]
        return categories.get(prefix, "")
    
    @staticmethod
    def process_dora(file_data) -> List[Dict]:
        """
        Process DORA regulations.
        
        Args:
            file_data: File-like object with DORA content
            
        Returns:
            List of controls in standard format
        """
        controls = []
        
        try:
            # Check if file_data is CSV
            if hasattr(file_data, 'read'):
                # Reset position
                file_data.seek(0)
                
                # Read as CSV
                reader = csv.reader(file_data)
                headers = next(reader, None)
                
                # Find relevant column indices
                article_col, title_col, desc_col = -1, -1, -1
                
                for i, header in enumerate(headers or []):
                    header_lower = header.lower()
                    if 'article' in header_lower:
                        article_col = i
                    elif 'title' in header_lower or 'name' in header_lower:
                        title_col = i
                    elif 'description' in header_lower or 'text' in header_lower or 'content' in header_lower:
                        desc_col = i
                
                if article_col == -1 or desc_col == -1:
                    # Try to guess columns if headers not identified
                    article_col, title_col, desc_col = 0, 1, 2
                
                # Parse rows
                for row in reader:
                    if len(row) <= max(article_col, desc_col):
                        continue  # Skip rows with insufficient columns
                    
                    article = row[article_col].strip()
                    title = row[title_col].strip() if title_col >= 0 and title_col < len(row) else ""
                    description = row[desc_col].strip()
                    
                    if article and description:
                        controls.append({
                            "id": article,
                            "name": title or f"DORA Article {article}",
                            "description": description,
                            "standard": "DORA",
                            "section": StandardSpecificHandler._extract_dora_section(article)
                        })
            else:
                # Treat as string content
                content = file_data
                
                # Simple regex-based parsing
                article_pattern = r'Article\s+(\d+(?:\.\d+)*)\s*[-:]\s*([^\n]+)'
                section_pattern = r'Section\s+\d+\s*:?\s*([^\n]+)'
                
                # Find articles
                article_matches = re.finditer(article_pattern, content, re.IGNORECASE)
                
                for match in article_matches:
                    article = match.group(1).strip()
                    description = match.group(2).strip()
                    
                    if article and description:
                        controls.append({
                            "id": f"Article {article}",
                            "name": f"DORA Article {article}",
                            "description": description,
                            "standard": "DORA",
                            "section": StandardSpecificHandler._extract_dora_section(article)
                        })
                
                # Also find sections
                section_matches = re.finditer(section_pattern, content, re.IGNORECASE)
                
                for match in section_matches:
                    description = match.group(1).strip()
                    
                    if description:
                        # Generate ID from text
                        section_id = re.sub(r'\W+', '_', description[:30]).lower()
                        
                        controls.append({
                            "id": section_id,
                            "name": description[:50],
                            "description": description,
                            "standard": "DORA",
                            "section": "General Provisions"
                        })
        
        except Exception as e:
            logger.error(f"Error processing DORA file: {e}")
            
        return controls
    
    @staticmethod
    def _extract_dora_section(article: str) -> str:
        """Extract DORA section from article ID."""
        # DORA sections: Articles 1-10 = General Provisions, etc.
        try:
            article_num = int(article.replace('Article', '').strip())
            
            if article_num <= 10:
                return "Chapter I: General Provisions"
            elif article_num <= 16:
                return "Chapter II: ICT Risk Management"
            elif article_num <= 25:
                return "Chapter III: Digital Operational Resilience Testing"
            elif article_num <= 31:
                return "Chapter IV: ICT Third-party Risk"
            else:
                return "Chapter V: Information Sharing"
        except:
            return "General Provisions"
    
    @staticmethod
    def process_owasp_ai(file_data) -> List[Dict]:
        """
        Process OWASP AI Exchange and Top 10 for LLMs.
        
        Args:
            file_data: File-like object with OWASP AI content
            
        Returns:
            List of controls in standard format
        """
        controls = []
        
        try:
            # Try to parse as JSON first
            if hasattr(file_data, 'read'):
                # Reset position
                file_data.seek(0)
                
                try:
                    # Parse JSON
                    data = json.load(file_data)
                    
                    # Handle OWASP Top 10 for LLM JSON format
                    if isinstance(data, dict) and ('categories' in data or 'risks' in data or 'controls' in data):
                        items = data.get('categories') or data.get('risks') or data.get('controls') or []
                        
                        for item in items:
                            item_id = item.get('id') or item.get('code')
                            name = item.get('name') or item.get('title')
                            description = item.get('description') or item.get('summary') or ""
                            
                            if name:
                                controls.append({
                                    "id": item_id or f"AI-{len(controls)+1}",
                                    "name": name,
                                    "description": description,
                                    "standard": "OWASP AI",
                                    "section": item.get('category') or "LLM Security"
                                })
                                
                                # Also add mitigations as separate controls if present
                                mitigations = item.get('mitigations') or []
                                for i, mitigation in enumerate(mitigations):
                                    if isinstance(mitigation, dict):
                                        mitigation_text = mitigation.get('description') or mitigation.get('text')
                                    else:
                                        mitigation_text = str(mitigation)
                                        
                                    controls.append({
                                        "id": f"{item_id}-M{i+1}",
                                        "name": f"Mitigation for {name}",
                                        "description": mitigation_text,
                                        "standard": "OWASP AI",
                                        "section": "Mitigations",
                                        "parent_id": item_id
                                    })
                    elif isinstance(data, list):
                        # Handle simple list format
                        for i, item in enumerate(data):
                            if isinstance(item, dict):
                                item_id = item.get('id') or f"AI-{i+1}"
                                name = item.get('name') or item.get('title')
                                description = item.get('description') or item.get('text') or ""
                                
                                if name:
                                    controls.append({
                                        "id": item_id,
                                        "name": name,
                                        "description": description,
                                        "standard": "OWASP AI",
                                        "section": "LLM Security"
                                    })
                
                except json.JSONDecodeError:
                    # Not valid JSON, try CSV
                    file_data.seek(0)
                    reader = csv.reader(file_data)
                    headers = next(reader, None)
                    
                    # Find relevant column indices
                    id_col, name_col, desc_col = -1, -1, -1
                    
                    for i, header in enumerate(headers or []):
                        header_lower = header.lower()
                        if 'id' in header_lower or 'code' in header_lower:
                            id_col = i
                        elif 'name' in header_lower or 'title' in header_lower:
                            name_col = i
                        elif 'description' in header_lower or 'text' in header_lower:
                            desc_col = i
                    
                    if name_col == -1:
                        # Try to guess columns if headers not identified
                        id_col, name_col, desc_col = 0, 1, 2
                    
                    # Parse rows
                    for i, row in enumerate(reader):
                        if len(row) <= name_col:
                            continue  # Skip rows with insufficient columns
                        
                        control_id = row[id_col].strip() if id_col >= 0 and id_col < len(row) else f"AI-{i+1}"
                        name = row[name_col].strip()
                        description = row[desc_col].strip() if desc_col >= 0 and desc_col < len(row) else ""
                        
                        if name:
                            controls.append({
                                "id": control_id,
                                "name": name,
                                "description": description,
                                "standard": "OWASP AI",
                                "section": "LLM Security"
                            })
            else:
                # Treat as string content
                content = file_data
                
                # Try to parse as JSON
                try:
                    data = json.loads(content)
                    
                    # Convert to file-like object and process
                    json_file = io.StringIO(content)
                    return StandardSpecificHandler.process_owasp_ai(json_file)
                    
                except json.JSONDecodeError:
                    # Simple regex-based parsing
                    risk_pattern = r'(LLM\d+|AI\d+):\s*([^\n]+)'
                    matches = re.finditer(risk_pattern, content, re.IGNORECASE)
                    
                    for match in matches:
                        risk_id = match.group(1).strip()
                        name = match.group(2).strip()
                        
                        if risk_id and name:
                            controls.append({
                                "id": risk_id,
                                "name": name,
                                "description": "",  # No description available in this format
                                "standard": "OWASP AI",
                                "section": "LLM Security"
                            })
        
        except Exception as e:
            logger.error(f"Error processing OWASP AI file: {e}")
            
        return controls
    
    @staticmethod
    def process_generic(file_data) -> List[Dict]:
        """
        Process a generic standard file (CSV or JSON).
        
        Args:
            file_data: File-like object with standard content
            
        Returns:
            List of controls in standard format
        """
        controls = []
        
        try:
            # Try JSON first
            if hasattr(file_data, 'read'):
                # Save position
                position = file_data.tell()
                
                try:
                    # Try parsing as JSON
                    data = json.load(file_data)
                    
                    # Process based on structure
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                control = StandardSpecificHandler._extract_control_from_dict(item)
                                if control:
                                    controls.append(control)
                    elif isinstance(data, dict) and any(key in data for key in ['controls', 'requirements', 'items']):
                        # Standard has a wrapper object
                        items = data.get('controls') or data.get('requirements') or data.get('items') or []
                        standard_name = data.get('name') or data.get('standard') or "Generic"
                        
                        for item in items:
                            if isinstance(item, dict):
                                control = StandardSpecificHandler._extract_control_from_dict(item, standard_name)
                                if control:
                                    controls.append(control)
                                    
                except json.JSONDecodeError:
                    # Reset position and try CSV
                    file_data.seek(position)
                    
                    reader = csv.reader(file_data)
                    headers = next(reader, None)
                    
                    if not headers:
                        return controls
                        
                    # Map headers to control fields
                    field_map = {}
                    for i, header in enumerate(headers):
                        header_lower = header.lower()
                        
                        if any(term in header_lower for term in ['id', 'number', 'identifier']):
                            field_map['id'] = i
                        elif any(term in header_lower for term in ['name', 'title']):
                            field_map['name'] = i
                        elif any(term in header_lower for term in ['desc', 'text', 'requirement']):
                            field_map['description'] = i
                        elif any(term in header_lower for term in ['section', 'category', 'group']):
                            field_map['section'] = i
                        elif any(term in header_lower for term in ['standard', 'framework']):
                            field_map['standard'] = i
                    
                    # Process rows
                    for row in reader:
                        control = {}
                        
                        for field, index in field_map.items():
                            if index < len(row):
                                control[field] = row[index].strip()
                        
                        # Ensure required fields
                        if 'name' in control and control['name']:
                            if 'id' not in control or not control['id']:
                                control['id'] = f"CTRL-{len(controls)+1}"
                            if 'standard' not in control:
                                control['standard'] = "Generic"
                                
                            controls.append(control)
        
        except Exception as e:
            logger.error(f"Error processing generic standard file: {e}")
            
        return controls
    
    @staticmethod
    def _extract_control_from_dict(item: Dict, standard_name: str = "Generic") -> Optional[Dict]:
        """Extract control from dictionary item."""
        control = {}
        
        # Map common field names
        for src, dst in [
            (['id', 'controlId', 'requirementId', 'number'], 'id'),
            (['name', 'title', 'heading'], 'name'),
            (['description', 'text', 'requirement', 'details'], 'description'),
            (['section', 'category', 'group', 'chapter'], 'section'),
            (['standard', 'framework', 'document'], 'standard')
        ]:
            for src_field in src:
                if src_field in item and item[src_field]:
                    control[dst] = item[src_field]
                    break
        
        # Ensure required fields
        if 'name' in control and control['name']:
            if 'id' not in control:
                control['id'] = f"CTRL-{hash(control['name']) % 10000}"
            if 'standard' not in control:
                control['standard'] = standard_name
            return control
        
        return None 