# -*- coding: UTF-8 -*-
'''
Copyright (c) 2018-2025 Prof. Jan Berger, Hochschule fuer Technik und Wirtschaft Berlin, Germany
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Autodesk® Maya® is a registered trademark of Autodesk Inc.
All other brand names, product names or trademarks belong to their respective holders.

Supported Maya Versions:
2022-2025

Supported OS:
Any OS supported by Maya

Thanks to:
- Simon Leykamm for various UI improvement suggestions regarding the FrameWdget and DPI-Scaling

'''


import sys
import json
import os
import math
import inspect
import shutil
import ast
import copy

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

import maya.cmds as mc
import maya.mel as mm

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya import OpenMayaUI as omui

maya_version = int( mc.about(version=True) )

if maya_version < 2025:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2 import QtCore
    from shiboken2 import wrapInstance
else:
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *
    from PySide6 import QtCore
    from shiboken6 import wrapInstance

from functools import partial

real_scale = mc.mayaDpiSetting(query=True, realScaleValue=True)

# override omui.MQtUtil.dpiScale px-function
def px(value):
    return real_scale*value

kPluginName    = 'aniMeta'
kPluginVersion = '01.00.157'

kLeft, kRight, kCenter, kAll, kSelection = range( 5 )
kHandle, kIKHandle, kJoint, kMain, kBodyGuide, kBipedRoot, kQuadrupedRoot, kCustomHandle, kBodyGuideLock, kBipedRootUE = range(10)
kBiped, kBipedUE, kQuadruped, kCustom = range(4)
kRigTypeString = ['Biped', 'BipedUE', 'Quadruped', 'Custom' ]
kLocal, kWorld, kParent = range(3)
kBasic, kSymmetricTranslation, kSymmetricRotation, kAuto = range( 4 )
kTorso, kArm, kHand, kLeg, kHead, kFace = range(6)
kPairBlend, kPairBlendTranslate, kPairBlendRotate = range(3)
kRigStateBind, kRigStateGuide, kRigStateControl = range(3)
kXYZ, kYZX, kZXY, kXZY, kYXZ, kZYX = range(6)
kX, kY, kZ = range(3)
kFK, kIK = range(2)
kLibPose, kLibAnim, kLibRig = range(3)

curveType = [ 'animCurveTA', 'animCurveTL', 'animCurveTT', 'animCurveTU',
              'animCurveUA', 'animCurveUL', 'animCurveUT', 'animCurveUU' ]

floatDataTypes = [ 'double', 'doubleLinear' ]

angleDataTypes = ['doubleAngle']

static, animCurve = range( 2 )

attrInput = [ 'static', 'animCurve' ]

floatPrec = 5

py_version = float( sys.version[0:3] )

def maya_useNewAPI():
    """
    We need this for Maya Python API 2.0
    """
    pass

class AniMeta( object ):

    aniMetaDataAttrName = 'aniMetaData'

    hik_side = [  'Center', 'Left',  'Right', 'None' ]

    hik_type = [ 'None', 'Root', 'Hip', 'Knee', 'Foot',
                'Toe', 'Spine', 'Neck', 'Head', 'Collar',
                'Shoulder', 'Elbow', 'Hand', 'Finger', 'Thumb',
                'PropA', 'PropB', 'PropC', 'Other', 'Index Finger',
                'Middle Finger', 'Ring Finger', 'Pinky Finger', 'Extra Finger', 'Big Toe',
                'Index Toe', 'Middle Toe', 'Ring Toe', 'Pinky Toe', 'Extra Toe']

    attrs    = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'ro', 'jox', 'joy', 'joz', 'side', 'type', 'radius' ]
    defaults = [ 0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  1.0,  1.0,  1.0,    0,   0.0,   0.0,   0.0,      0,      0,        1 ]
    kBasic, kSymmetricTranslation, kSymmetricRotation = range( 3 )
    kParent, kOrient, kPoint, kAim = range(4)
    kCube, kSphere, kPipe = range(3)

    ui = None

    def __init__( self ):

        self.workspace = mc.workspace( query=True, fn=True )
        self.folder_aniMeta = 'aniMeta'
        self.folder_pose = os.path.join( self.workspace, self.folder_aniMeta, 'Pose' )
        self.folder_anim = os.path.join( self.workspace, self.folder_aniMeta, 'Anim' )
        self.folder_rig = os.path.join( self.workspace, self.folder_aniMeta, 'Rig' )

        self.check_folder( self.folder_pose )
        self.check_folder( self.folder_anim )
        self.check_folder( self.folder_rig )

        # Required plug-in that may or may not already be loaded
        mc.loadPlugin("mayaHIK", quiet=True)

    def check_folder (self, folder):

        if not os.path.isdir( folder ):
            try:
                os.makedirs( folder )
            except:
                mc.warning('aniMeta: There was a problem creating folder', folder)


    def create_ui( self, *args ):

        self.ui = AniMetaUI()
        self.update_ui()

    def find_node( self, root, nodeName ):
        '''
        Finds a DAG node within the specified character node, useful when multiple rigs are present.
        :param root: The character`s name.
        :param nodeName: The DAG node to look for
        :return: A string with the long DAG path to the node or None if the node is not found.
        '''
        if nodeName is None:
            return None
        if root is None:
            return None
        nodeNameShort = self.short_name(nodeName)

        if not root:
            mc.warning( 'aniMeta: Character is not specified, please select it from the Character Editor.')

        # Remove colons in case rig is referenced
        if ':' in nodeNameShort:
            buff = nodeNameShort.split(':')
            nodeNameShort = buff[len(buff) - 1]

        nodes = mc.listRelatives( root, ad=True, c=True, f=True, pa=True) or []

        for node in nodes:
            currentNode = self.short_name(node)

            # Remove colons in case rig is referenced
            if ':' in currentNode:
                buff = currentNode.split(':')
                currentNode = buff[len(buff) - 1]
            if currentNode == nodeNameShort:

                return node
        return None


    def get_active_char( self ):
        '''
        Gets the selected character from the character list.
        :return: the selected character
        '''

        list = self.get_char_list()

        if list is not None:
            count = list.count()
            if count > 0:
                char = list.currentText()
                if mc.objExists( char ):
                    return char
                else:
                    return None
        else:
            return None

    def get_char_type(self):

        rootNode = self.get_active_char()
        rootData = self.get_metaData(rootNode)

        # We leave the first variant here for now for compatibility reasons
        if 'RigType' in rootData:
            return rootData['RigType']
        else:
            return None


    def get_char_list( self ):

        ptr = None

        try:
            ptr = omui.MQtUtil.findControl( 'aniMetaUI' )
        except:
            #mc.warning( 'aniMeta find char: Can not find UI.' )
            return None
        widget = None

        try:
            if py_version < 3:
                widget = wrapInstance( long( ptr ), QWidget )
            else:
                # Python 3 doesn`t featrue the long data type anymore, so we can simply use int
                widget = wrapInstance( int( ptr ), QWidget )
        except:
            mc.warning( 'aniMeta find char: please select a character in the character editor' )
            return None

        list = None
        try:
            list = widget.findChild( QComboBox, 'aniMetaCharList' )

        except:
            #mc.warning( 'aniMeta find char: Can not find character list.' )
            return None

        return list


    def get_metaData( self, node, attr = aniMetaDataAttrName ):
        data = { }
        try:
            if mc.attributeQuery( attr, exists = True, node = node ):
                data = eval( mc.getAttr( node + '.' + attr ) )
        except:
            pass
        return data

    def get_nodes( self, root, dict = None, attr = aniMetaDataAttrName, hierarchy = True ):

        if dict is None:
            dict = { }
        if root is not None:
            if hierarchy:
                if not mc.objExists( root ):
                    mc.warning( root + ' does not exist.' )
                    return False
            else:
                if len( root ) > 0:
                    for r in root:
                        if not mc.objExists( r ):
                            mc.warning( 'Object ' + r + ' does not exist.' )
        if len( dict ) == 0:
            mc.warning( 'Please specify which metaData to look for.' )
            return False

        keys = sorted( dict.keys() )
        keyCount = len( dict.keys() )

        nodes = [ ]
        if hierarchy:
            nodes = mc.listRelatives( root, children = True, ad = True, pa = True ) or [ ]
            nodes.append( root )
        else:
            nodes = root
        if root is None:
            nodes = mc.ls()

        matches = [ ]
        for node in nodes:
            if self.match_metaData( node, dict ):
                # The IK nodes have pipes and we dont want those here
                if '|' in node:
                    node = node.split('|')
                    node = node[ len( node ) - 1 ]
                matches.append( node )
        matches = sorted( matches )
        return matches

    def get_mobject( self, node ):

        if isinstance( node, om.MDagPath ):
            return node.node()

        try:
            list = om.MSelectionList()
            list.add( node )
            obj = list.getDependNode( 0 )

            return obj
        except:
            print ( 'Can not get an MObject from ', node )
            return None


    def get_path ( self, nodeName, showWarnings=True ):
        '''
        Returns the MDagPath of a given maya node`s string name, the verbose flag enables/disables warnings
        :rtype:
        '''
        if isinstance( nodeName, om.MDagPath ):
            return nodeName

        # Check if more than object with this name exists in the scene
        if len(mc.ls(nodeName))  > 1:
            mc.warning('AniMeta->Get Path: More than one object matches name ' + nodeName)
            return None

        if nodeName is not None:
            obj = self.get_mobject( nodeName )

            if obj is not None:
                dagPath = om.MDagPath()
                if obj != om.MObject().kNullObj :
                    dagPath = om.MDagPath.getAPathTo( obj )
                else:
                    if showWarnings:
                        print( 'get_path: can not get a valid MDagPath:', nodeName)
                        return None

                return dagPath
        return None

    def get_scene_info( self ):
        dict = { }

        dict[ 'time' ]     = mc.currentUnit( query = True, time = True )
        dict[ 'angle' ]    = mc.currentUnit( query = True, angle = True )
        dict[ 'linear' ]   = mc.currentUnit( query = True, linear = True )
        dict[ 'fileName' ] = mc.file( q = True, sceneName = True )
        dict[ 'maya' ]     = mc.about( version = True )
        dict[ 'aniMeta' ]  = kPluginVersion

        return dict

    def match_metaData( self, node = 'myNode', dict = None ):
        '''
        Returns True if the given node`s metaData attr dict matches the Keys and Values of the dict argument

        :param node: the node to check
        :param dict: the dictionary with the matching criteria
        :return: True if it matches ALL keys and values, otherwise returns False
        '''
        if dict is None:
            dict = { }

        metaData = self.get_metaData( node )

        if len( metaData ) > 0:

            keys = sorted( dict.keys() )
            keyCount = len( dict.keys() )

            matches = [ ]

            if len( metaData ) > 0:
                keyMatch = 0
                for key in keys:
                    if key in metaData:
                        if dict[ key ] == metaData[ key ]:
                            keyMatch += 1
                        # if we want both sides ...
                        # before it was just if, keeping an eye on it
                        elif key == 'Side' and dict[ 'Side' ] == kAll:
                            keyMatch += 1

                if keyMatch == keyCount:
                    return True
        return False

    def set_attr( self, node, attr, value, setKeyframe = False ):

        if isinstance( node, om.MDagPath ):
            node = node.fullPathName()

        if mc.objExists( node ):
            if mc.objExists( node + '.' + attr ):
                if mc.getAttr( node + '.' + attr, se = True ):
                    if setKeyframe is False:
                        mc.setAttr( node + '.' + attr, value )
                    else:
                        mc.setKeyframe( node, attribute = attr, value = value )
                else:
                    mc.warning('AniMeta->set_attr: Node Attribute is not settable '+node+'.'+ attr)
            else:
                mc.warning('AniMeta->set_attr: Node Attribute does not exist '+node+'.'+ attr)
        else:
            mc.warning('AniMeta->set_attr: Node does not exist '+node)

    def set_metaData( self, node, data = None, attr = aniMetaDataAttrName ):
        if data is None:
            data = { }

        node_path = self.get_path( node )

        if node_path is not None:
            if not mc.attributeQuery( attr, exists = True, node = node_path.fullPathName() ):
                mc.addAttr( node_path.fullPathName(), ln = attr, dt = "string" )
            mc.setAttr( node_path.fullPathName() + '.' + attr, str( data ), typ = 'string' )

    def short_name( self,  node ):
        if node is not None:
            if isinstance( node, str ) :
                buff = node.split('|')
                return buff[len(buff)-1]
            elif isinstance( node, om.MDagPath ):
                buff = node.fullPathName().split('|')
                return buff[len(buff)-1]
            else:
                print('aniMeta.short_name: unknown node type ', node ,  node.__class__.__name__ )
        else:
            return None

    def update_ui( self, *args, **kwargs ):

        ptr = omui.MQtUtil.findControl( 'aniMetaUI' )

        if ptr is not None:
            ui = AniMetaUI( create = False )
            ui.char_list_refresh()

            if 'picker' in kwargs:
                ui = AniMetaUI( create = True )
                ui.char_list_refresh()

            if 'rig' in kwargs:
                ui.set_active_char(kwargs['rig'])


class Menu(AniMeta):

    menuName   = 'aniMeta'
    mainWindow = 'MayaWindow'
    menu       = None

    def create( self ):

        char       = Char()

        self.delete()

        self.menu = mc.menu( self.menuName, parent = self.mainWindow )

        ######################################################################################
        #
        # Menu

        mc.menuItem( label = 'Character Editor', c= self.create_ui  )

        ##################################################################################
        #
        # Character

        mc.menuItem( label = 'Character', sm = True, to = True, parent = self.menu )

        mc.menuItem( label = 'Create', divider=True )
        mc.menuItem( label = 'Biped UE',    c = partial( char.create, name='Adam', type=kBipedUE ) )

        # Character
        #
        ##################################################################################

        ##################################################################################
        #
        # Rigging

        riggingMenu = mc.menuItem( label = 'Rig', sm = True, to = True, parent = self.menu )

        rig  = Rig()

        mc.setParent( riggingMenu, menu = True )
        mc.menuItem( label = 'Orient Transform', c = Orient_Transform_UI )
        mc.menuItem( d = True, dl = 'Control Handles' )
        mc.menuItem( label = 'Create Custom Control', c = rig.create_custom_control )
        mc.menuItem( label = 'Delete Custom Control', c = rig.delete_custom_control )
        mc.menuItem( d = True, dl = 'Grouping' )
        mc.menuItem( label = 'Create Null', c = rig.create_nul )
        mc.menuItem( d = True, dl = 'Symmetry Constraint' )
        mc.menuItem( label = 'Create', c = rig.create_sym_con )
        mc.menuItem( label = 'Hierarchy', c = rig.create_sym_con_hier )

        mc.menuItem( d = True, dl = 'Joystick Widgets' )
        mc.menuItem( label = 'Create ...', c = rig.create_joystick_widget_ui )

        mc.menuItem( d = True, dl = 'Hierarchy I/O' )
        mc.menuItem( label = 'Export Hierarchy ...', c = rig.export_joints_ui )
        mc.menuItem( label = 'Import Hierarchy ...', c = rig.import_joints_ui )

        mc.menuItem( d = True, dl = 'Driven Keys I/O' )
        mc.menuItem( label = 'Export Driven Keys ...', c = rig.export_drivenKeys_ui )
        mc.menuItem( label = 'Import Driven Keys ...', c = rig.import_drivenKeys_ui )

        # Rigging
        #
        ##################################################################################

        ##################################################################################
        #
        # Skinning

        riggingMenu = mc.menuItem( label = 'Skinning', sm = True, to = True, parent = self.menu )

        skin = Skin()

        mc.menuItem( d = True, dl = 'Skinning' )
        mc.menuItem( label = 'Bind Skin',             c = skin.bind )
        mc.menuItem( label = 'Smooth Weights',        c = skin.smooth )
        mc.menuItem( label = 'Smooth Weights Tool',   c = skin.smooth_tool )
        mc.menuItem( label = 'Reset Skin Influences', c = skin.reset )
        mc.menuItem( label = 'Transfer Skinning',     c = skin.transfer )
        mc.menuItem( label = 'Mirror Skin Weights',   c = skin.mirror )

        mc.menuItem( d = True, dl = 'Skinning I/O ' )
        mc.menuItem( label = 'Export Skinning ...', c = skin.export_ui )
        mc.menuItem( label = 'Import Skinning ...', c = skin.import_ui )


        # Skinning
        #
        ##################################################################################

        ##################################################################################
        #
        # Transform

        mc.menuItem( label = 'Transform', sm = True, to = True, parent = self.menu )

        xform           =  Transform()
        xform_mirror_ui =  TransformMirrorUI()

        mc.menuItem( label = 'Copy',   c = xform.copy )
        mc.menuItem( label = 'Paste',  c = xform.paste )
        mc.menuItem( label = 'Mirror', c = xform_mirror_ui.mirror )
        mc.menuItem( optionBox = True, c = xform_mirror_ui.ui )

        mc.menuItem( d = True, dl = 'Joints' )
        mc.menuItem( label = 'Zero Out Joint Rotation', c = xform.zero_out_joint_orient    )
        mc.menuItem( label = 'Zero Out to Offset Parent', c = xform.zero_out_to_offsetParent )

        # Transform
        #
        ##################################################################################

        ##################################################################################
        #
        # Modeling

        model = Model()
        model_sym_ui =  ModelSymExportUI()

        model_menu = mc.menuItem( label = 'Model', sm = True, to = True, parent = self.menu )

        mc.menuItem( label = 'Mirror Geometry', c = model.mirror_geo, parent = model_menu )
        mc.menuItem( label = 'Split BlendShape', c = BlendShapeSplitter, parent = model_menu )
        mc.menuItem( d = True, dl = 'Symmetry' )
        mc.menuItem( label = 'Flip Points', c = model.flip_geo, parent = model_menu )
        mc.menuItem( label = 'Mirror Points', c = model.mirror_points, parent = model_menu )
        mc.menuItem( label = 'Export Symmetry', c = model_sym_ui.ui, parent = model_menu )
        mc.menuItem( label = 'Specify Symmetry File ...', c = model.specify_symmetry_file_ui, parent = model_menu )
        mc.menuItem( d = True, dl = '' )
        mc.menuItem( label = 'Extract Faces', c = model.duplicate_extract_soften_faces, parent = model_menu )

        # Modeling
        #
        ##################################################################################

        ##################################################################################
        #
        # Misc

        mc.setParent( self.menu, menu = True )

        mc.menuItem( divider = True )

        mc.menuItem( label = 'Options...', c=AniMetaOptionsUI)

        #mc.menuItem( label = 'Documentation...',
        #             c = 'import maya.cmds as cmds\ncmds.launch(web="https://htw3d.readthedocs.io/en/latest/")' )

        #mc.menuItem( label = 'About ...',
        #             c = 'import maya.OpenMaya\nmaya.OpenMaya.MGlobal.displayInfo("' + kPluginName + ' version ' + kPluginVersion + ', written by Jan Berger")' )

        # Misc
        #
        ##################################################################################

        # Menu
        #
        ######################################################################################

    def delete( self ):

        if mc.menu( self.menuName, exists = True ):
            mc.deleteUI( self.menuName )

######################################################################################
#
# Transform

class Transform(AniMeta):

    xforms = {}

    def __init__(self):
        super( Transform, self ).__init__()

    def copy( self, *args, **kwargs ):

        sel = mc.ls( sl = True )

        xDict = { }

        if sel is not None:

            for s in sel:
                xDict[ self.short_name( s ) ] = self.get_matrix( node = s, space = kWorld )

            self.xforms = xDict

    def create_matrix( self, translate = om.MVector( 0, 0, 0 ), rotate = om.MEulerRotation( 0, 0, 0, 0 ),
                       scale = ( 1, 1, 1 ) ):

        tmat = om.MTransformationMatrix()
        rmat = om.MTransformationMatrix( rotate.asMatrix() )
        smat = om.MTransformationMatrix()

        # Translate
        tmat.setTranslation( translate, om.MSpace.kTransform )

        # Scale
        smat.setScale( scale, om.MSpace.kTransform )

        return smat.asMatrix() * rmat.asMatrix() * tmat.asMatrix()


    def get_translate( self, matrix ):
        '''Returns the translate component of a given matrix'''
        matrixT = om.MTransformationMatrix( matrix )
        return matrixT.translation( om.MSpace.kTransform )

    def get_matrix( self, node, space=kWorld):
        '''Returns the transformation of certain DAG nodes in local or world space as MMatrix object.'''

        obj1 = self.get_mobject(node)

        if obj1 is None:
            return None

        if ( obj1.apiType() == om.MFn.kTransform or obj1.apiType() == om.MFn.kJoint or obj1.apiType() == om.MFn.kIkHandle):

            dagFn1 = om.MFnDagNode(obj1)
            dagPath1 = dagFn1.getPath()

            if space == kLocal:

                transFn = om.MFnTransform(dagPath1)

                t = transFn.translation(om.MSpace.kTransform)
                translate = om.MTransformationMatrix()
                translate.setTranslation(t, om.MSpace.kTransform)

                rotate = transFn.rotation(om.MSpace.kTransform)

                s = om.MVector(transFn.scale())

                scale = om.MTransformationMatrix()
                scale.setScale(s, om.MSpace.kTransform)

                return scale.asMatrix() * rotate.asMatrix() * translate.asMatrix()

            elif space == kWorld:

                return dagPath1.inclusiveMatrix()

            elif space == kParent:

                return dagPath1.exclusiveMatrix()

            else:
                print ('Invalid input, please specify 1 transform nodes by DAG path name, these were received: ', node)
                return []
        else:
            #print ('get: invalid node type specfified: ', node, mc.nodeType(node))
            return None

    def invert_matrix(self, matrix ):
        tmat = om.MTransformationMatrix( matrix )
        return tmat.asMatrixInverse()

    def print_matrix(self, matrix, text=''):

        t = self.get_translate(matrix)
        r = self.get_rotate(matrix)
        s = self.get_scale(matrix)

        print( text )
        print( 'Translate:', round( t[0], 5 ), round( t[1], 5 ), round( t[2], 5 ) )
        print( 'Rotate:   ', round( math.degrees(r[0]), 5 ), round( math.degrees(r[1]), 5 ), round( math.degrees(r[2]), 5 ) )
        print( 'Scale:    ', round( s[0], 5 ), round( s[1], 5 ), round( s[2], 5 ) )

    def get_rotate( self, matrix ):
        '''Returns the rotate component of a given matrix'''
        matrixT = om.MTransformationMatrix( matrix )
        return matrixT.rotation()

    def get_polevector_position(self, dagPath_1, dagPath_2, dagPath_3, preferredAngle=(45.0, 0.0, 0.0)):
        '''
        Calulates the Position for the Pole Vector
        :param dagPath_1: Start IK node ( ie Upper Leg )
        :param dagPath_2: Effector IK node ( ie Knee )
        :param dagPath_3: Handle IK node ( ie Foot )
        :param preferredAngle: The preferred angle of the IK Solver.
        :return: MVector with the world position
        '''

        # Preferred Angle
        pa = om.MVector(45.0, 0.0, 0.0)
        pa.x = math.radians(preferredAngle[0])
        pa.y = math.radians(preferredAngle[1])
        pa.z = math.radians(preferredAngle[2])

        dag1WorldTMat  = self.get_matrix( dagPath_1, kWorld )
        dag2WorldTMat  = self.get_matrix( dagPath_2, kWorld )
        dag3WorldTMat  = self.get_matrix( dagPath_3, kWorld )

        # Redundant? Should be just identity ...
        m1 = dag1WorldTMat
        m2 = dag2WorldTMat * self.invert_matrix( dag1WorldTMat )
        m3 = dag3WorldTMat * self.invert_matrix( dag1WorldTMat )

        L1 = self.get_translate( m1 )
        L2 = self.get_translate( m2 )
        L3 = self.get_translate( m3 )

        V1 = self.get_translate( m2 ) #- L1
        V2 = L3 - L2
        V3 = self.get_translate( m3 ) #L1 - L3

        angle = V1.angle(V2)

        angle = round( angle, 4 )

        if abs(angle) > 0.001:
            # There is an angle

            a_vec = self.get_translate( m2 )
            c_vec = self.get_translate( m3 )

            # Get the angle beta
            beta = a_vec.angle(c_vec)

            # Get the length of the sides
            a = a_vec.length()
            c = c_vec.length()

            # Trigonometry derived from sin(alpha)= h / b
            h = math.sin( beta ) * a

            # q is the length along c to the point that divides the triangle into two square triangles
            q = math.cos( beta ) * a

            # scale vector c so it has the length q
            c_vec.normalize()
            c_vec *= q

            # Calculate the vector h to get the axis along the height of the triangle and scale it so it has the length of c
            h_vec = a_vec - c_vec
            h_vec.normalize()
            h_vec *= c
            # The pole vector position is the sum of the vectors h and c
            pole_pos = h_vec + c_vec

            # This is the relative pole Position in relation to the root joint
            pole_pos_mat = self.create_matrix(translate=pole_pos)

            # Pole vector position in world space
            return  pole_pos_mat * dag1WorldTMat

        else:
            # there is no angle
            pa.normalize()

            L4 = L2 + pa
            V4 = L4 - L2

            cross = om.MVector()
            cross.x = V2.y * V4.z - V4.y * V2.z
            cross.y = V4.x * V2.z - V2.x * V4.z
            cross.z = V2.x * V4.y - V2.y * V4.x

            poleOffset = om.MTransformationMatrix()
            poleOffset.setTranslation(cross, om.MSpace.kWorld)

            outMat = poleOffset.asMatrix() * dag2WorldTMat

            worldTrans = self.get_translate( outMat )

            ''', 'PoleOffset
            pa.normalize()
            L4 = L2 + pa
            V4 = L4 - L2
            cross = om.MVector()
            cross.x = V2.y * V4.z - V4.y * V2.z
            cross.y = V4.x * V2.z - V2.x * V4.z
            cross.z = V2.x * V4.y - V2.y * V4.x
            # Hack
            cross.x = 50 * pa.x
            cross.y = 50 * pa.y
            cross.z = 50 * pa.z
            poleOffset = om.MTransformationMatrix()
            poleOffset.setTranslation(cross, om.MSpace.kWorld)
            outMat = poleOffset.asMatrix() * dag2WorldTMat
            worldTrans = self.get_translate( outMat )
            '''
        return self.create_matrix(translate=worldTrans)

    def get_rotation_order( self, order ):
        if order == 0:
            return om.MEulerRotation.kXYZ
        elif order == 1:
            return om.MEulerRotation.kYZX
        elif order == 2:
            return om.MEulerRotation.kZXY
        elif order == 3:
            return om.MEulerRotation.kXZY
        elif order == 4:
            return om.MEulerRotation.kYXZ
        elif order == 5:
            return om.MEulerRotation.kZYX
        else:
            return om.MEulerRotation.kXYZ

    def get_scale( self, matrix ):
        '''Returns the scale component of a given matrix'''
        matrixT = om.MTransformationMatrix( matrix )
        return matrixT.scale( om.MSpace.kTransform )

    def list_to_matrix( self, matrix_list ):
        ''' Creates an MMatrix instance from a list with 16 float values.'''

        if len( matrix_list ) == 16:
            matrix = om.MMatrix()
            no = 0
            for i in range( 4 ):
                for j in range( 4 ):
                    matrix.setElement( i, j, matrix_list[ no ] )
                    no += 1
            return matrix
        else:
            return None

    def matrix_to_list( self, matrix ):
        ''' Creates a list with 16 float values from a MMatrix instance.'''

        m_list = [ ]
        for i in range( 4 ):
            for j in range( 4 ):
                m_list.append( round( matrix.getElement( i, j ), 6 ) )

        return m_list

    def mirror_matrix( self, matrix, mode = kSymmetricRotation, space = kLocal, refObect = '', axis=kX ):

        t = self.get_translate( matrix )
        r = self.get_rotate( matrix )
        s = self.get_scale( matrix )

        if axis == kX:
            t.x *= -1
            r.y *= -1
            r.z *= -1
            offset_x = math.radians( 180 )
        elif axis == kY:
            t.y *= -1
            r.x *= -1
            r.z *= -1
            offset_y = math.radians( 180 )
        else:
            t.z *= -1
            r.x *= -1
            r.y *= -1
            offset_z = math.radians( 180 )

        if mode == kSymmetricTranslation:
            s[ 0 ] *= -1

        elif mode == kSymmetricRotation:

            if space == kWorld:
                offset = om.MEulerRotation( offset_x, offset_y, offset_z )
                mirror_rotation = offset.asMatrix() * r.asMatrix()
                r = self.get_rotate( mirror_rotation )

            if space == kLocal:
                t = self.get_translate( matrix )
                t.x *= -1
                t.y *= -1
                t.z *= -1

                r = self.get_rotate( matrix )

        elif mode == kBasic:
            doNothing = 1
        else:
            print('mirrorMatrix: invalid mode')

        return self.create_matrix( translate = t, rotate = r, scale = s )

    def paste( self, *args, **kwargs ):

        sel = mc.ls( sl = True )

        xDict = self.xforms

        if sel is not None and xDict is not None:

            # Python3
            keys = list( xDict.keys() )

            # if there is only one transform in the dict, apply to all selected objects
            if len( keys ) == 1:
                for s in sel:
                    self.set_matrix( node = s, matrix = xDict[ keys[ 0 ] ], space = kWorld )
            # otherwise match the transformation one by one
            else:
                for s in sel:
                    if s in xDict:
                        self.set_matrix( node = s, matrix = xDict[ s ], space = kWorld )

    def match_transform(self, node, target, space = kWorld ):

        m = None

        if mc.objExists( target ):
            m = self.get_matrix( target, space )

        if mc.objExists( node ) and m:
            self.set_matrix( node, m, space )

            return True


    def set_matrix( self, node, matrix, space = kWorld, setKeyframe = False, setTranslate=True, setRotate=True, setScale=True ):

        if not isinstance( node, om.MDagPath ):
            path = self.get_path( node )
            if path is None:
                mc.warning('aniMeta: Couldn`t get a path to' + node )
            else:
                node = path

        if not isinstance( matrix, om.MMatrix ):
            mc.warning( 'aniMeta: Invalid matrix object for node ' + node.partialPathName())
            return False

        if space == kLocal:
            t = self.get_translate( matrix )
            r = self.get_rotate( matrix )
            s = self.get_scale( matrix )

            # Translate
            if setTranslate:
                self.set_attr( node, "tx", t.x, setKeyframe )
                self.set_attr( node, "ty", t.y, setKeyframe )
                self.set_attr( node, "tz", t.z, setKeyframe )

            # Rotate
            if setRotate:
                rotOrder = mc.getAttr( node.fullPathName() + '.rotateOrder' )

                if rotOrder != 0:
                    r.reorderIt( self.get_rotation_order( rotOrder ) )

                self.set_attr( node, "rx", math.degrees( r.x ), setKeyframe )
                self.set_attr( node, "ry", math.degrees( r.y ), setKeyframe )
                self.set_attr( node, "rz", math.degrees( r.z ), setKeyframe )

            # Scale
            if setScale:
                self.set_attr( node, "sx", s[ 0 ], setKeyframe )
                self.set_attr( node, "sy", s[ 1 ], setKeyframe )
                self.set_attr( node, "sz", s[ 2 ], setKeyframe )

        elif space == kWorld:

            obj1 = self.get_mobject( node )

            if (obj1.apiType() == om.MFn.kTransform or obj1.apiType() == om.MFn.kJoint):

                # get stuff
                dagFn1 = om.MFnDagNode( obj1 )

                #dagPath1 = om.MDagPath()

                dagPath1 = dagFn1.getPath()

                parentMat = om.MTransformationMatrix( dagPath1.exclusiveMatrix() )

                out_matrix = matrix * parentMat.asMatrixInverse()

                if obj1.apiType() is om.MFn.kJoint:
                    joPlug = dagFn1.findPlug( 'jointOrient', False )
                    joPlugX = joPlug.child( 0 )
                    joPlugY = joPlug.child( 1 )
                    joPlugZ = joPlug.child( 2 )

                    jo_matrix = om.MTransformationMatrix(
                        om.MEulerRotation( joPlugX.asDouble(), joPlugY.asDouble(), joPlugZ.asDouble() ).asMatrix() )

                    t = self.get_translate( out_matrix )

                    r = self.get_rotate( out_matrix )

                    s = self.get_scale( out_matrix )

                    r_matrix = r.asMatrix() * jo_matrix.asMatrixInverse()

                    r = self.get_rotate( r_matrix )

                    out_matrix = self.create_matrix( t, r, s )

                self.set_matrix( node, out_matrix, kLocal, setKeyframe, setTranslate, setRotate, setScale )

            else:
                print('Invalid input, please specify 1 transform nodes by DAG path name, these were received: ', node)
                return [ ]
        else:
            print('set: invalid space specfified: ', space)

    def zero_out_joint_orient( self,  *args ):
        sel = []
        if len( args ) > 0:
            for a in args:
                if mc.objExists( a ):
                    sel.append( a )
        if not sel:
            sel = mc.ls(sl=True)

        for s in sel:
            r = self.get_matrix( s, space=kLocal )
            obj = self.get_mobject( s )
            dagFn1 = om.MFnDagNode( obj )
            joPlug = dagFn1.findPlug('jointOrient', False)
            joPlugX = joPlug.child(0)
            joPlugY = joPlug.child(1)
            joPlugZ = joPlug.child(2)

            jo = om.MTransformationMatrix(
                om.MEulerRotation(joPlugX.asDouble(), joPlugY.asDouble(), joPlugZ.asDouble()).asMatrix())

            m =  r * jo.asMatrix()

            r = self.get_rotate(m)
            r.reorderIt(0)

            mc.setAttr(s + '.r', 0, 0, 0)
            mc.setAttr(s + '.jo', math.degrees(r.x), math.degrees(r.y), math.degrees(r.z))

    def zero_out_to_offsetParent( self,  *args ):

        sel = [ ]
        if len( args ) > 0:
            for a in args:
                if mc.objExists( a ):
                    sel.append( a )
        if not sel:
            sel = mc.ls( sl = True )

        for s in sel:

            try:
                # TODO consider existing matrix @ offsetparentMatrix
                m = mc.getAttr( s + '.matrix')

                mc.setAttr( s + '.offsetParentMatrix', m, typ='matrix')

                mc.setAttr( s + '.t', 0, 0, 0 )
                mc.setAttr( s + '.r', 0, 0, 0 )
                mc.setAttr( s + '.s', 1, 1, 1 )

                if mc.nodeType( s) =='joint':
                    mc.setAttr( s + '.jo', 0, 0, 0 )

            except:
                mc.warning('aniMeta: Can not zero out '+s)

# Transform
#
######################################################################################

######################################################################################
#
# Transform Mirror UI


class TransformMirrorUI( Transform ):

    ui_name = 'MirrorTransform'
    title = 'Mirror Transform'
    width = 300
    height = 280

    mode_ctrl = None
    attr_ctrl = None
    axis_ctrl = None

    def __init__( self ):
        super( TransformMirrorUI, self ).__init__()

    def ui( self, *args ):

        # Loesch das Fenster, wenn es bereits existiert
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

        mc.window( self.ui_name, title = self.title, width = self.width, height = self.height, sizeable = False )

        # Layout fuer Menus
        mc.menuBarLayout()

        # Edit Menu
        mc.menu( label = 'Edit' )

        # Edit Menu Items
        mc.menuItem( label = 'Save Settings', command = self.save_settings )
        mc.menuItem( label = 'Reset Settings', command = self.reset_settings )

        # Edit Menu
        mc.menu( label = 'Help' )
        mc.menuItem( label = 'Help on ' + self.title )

        form = mc.formLayout()

        mirror_button = mc.button( label = self.title, command = self.mirror_button_cmd )
        apply_button = mc.button( label = 'Apply', command = self.apply_button_cmd )
        close_button = mc.button( label = 'Close', command = self.delete )

        mode_label = mc.text( label = 'Mirror Mode' )
        attr_label = mc.text( label = 'Mirror Attributes' )
        axis_label = mc.text( label = 'Mirror Axis' )

        self.mode_ctrl = mc.radioButtonGrp(
            label = '',
            vertical = True,
            cw = (1, 60),
            labelArray3 = [ 'Default', 'Translate Behaviour', 'Rotate Behaviour' ],
            numberOfRadioButtons = 3,
            changeCommand = self.save_settings
        )

        self.attr_ctrl = mc.checkBoxGrp(
            numberOfCheckBoxes = 2,
            labelArray2 = [ 'Translate', 'Rotate' ],
            vertical = True,
            changeCommand = self.save_settings
        )

        self.axis_ctrl = mc.radioButtonGrp(
            label = '',
            vertical = False,
            cw4 = (0, 40, 40, 40),
            labelArray3 = [ 'X', 'Y', 'Z' ],
            numberOfRadioButtons = 3,
            changeCommand = self.save_settings
        )
        mc.formLayout(
            form,
            edit = True,
            attachForm = [
                (mode_label, 'top', 10),
                (mode_label, 'left', 45),
                (attr_label, 'left', 45),
                (axis_label, 'left', 45),
                (mirror_button, 'bottom', 5),
                (mirror_button, 'left', 5),
                (close_button, 'bottom', 5),
                (close_button, 'right', 5),
                (apply_button, 'bottom', 5),
                (self.mode_ctrl, 'left', 35),
                (self.mode_ctrl, 'top', 15),
                (self.attr_ctrl, 'left', 95),
                (self.axis_ctrl, 'left', 95) ],

            attachPosition = [ (mirror_button, 'right', 5, 33),
                               (close_button, 'left', 5, 66),
                               (apply_button, 'right', 0, 66),
                               (apply_button, 'left', 0, 33) ],

            attachControl = [ (self.mode_ctrl, 'top', 5, mode_label),
                              (attr_label, 'top', 15, self.mode_ctrl),
                              (self.attr_ctrl, 'top', 5, attr_label),
                              (axis_label, 'top', 15, self.attr_ctrl),
                              (self.axis_ctrl, 'top', 15, axis_label) ]
        )
        self.restore_settings()

        mc.showWindow()

    def mirror_button_cmd( self, *args ):

        # Fuehrt den Mirror Befehl aus
        self.mirror()

        # Schliesst das Interface
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

    def apply_button_cmd( self, *args ):

        # Fuehrt den Mirror Befehl aus
        self.mirror()

    def delete( self, *args ):

        # Schliesst das Interface
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

    def save_settings( self, *args ):

        # RadioButtonGrp indeices are 1-based and the actual mode inidces are zero-based
        # so we need to compensate by substracting 1
        mode = mc.radioButtonGrp( self.mode_ctrl, query = True, select = True ) -1
        mirror_t = mc.checkBoxGrp( self.attr_ctrl, query = True, value1 = True )
        mirror_r = mc.checkBoxGrp( self.attr_ctrl, query = True, value2 = True )
        axis = mc.radioButtonGrp( self.axis_ctrl, query = True, select = True ) -1

        mc.optionVar( intValue = ('aniMetaMirrorTrans_Mode', mode) )
        mc.optionVar( intValue = ('aniMetaMirrorTrans_AttrT', mirror_t) )
        mc.optionVar( intValue = ('aniMetaMirrorTrans_AttrR', mirror_r) )
        mc.optionVar( intValue = ('aniMetaMirrorTrans_Axis', axis) )

    def restore_settings( self, *args ):

        if not mc.optionVar( exists = 'aniMetaMirrorTrans_Mode' ):
            self.reset_settings()

        # RadioButtonGrp indeices are 1-based and the actual mode inidces are zero-based
        # so we need to compensate by adding 1
        mode = mc.optionVar( query = 'aniMetaMirrorTrans_Mode' ) + 1
        mirror_t = mc.optionVar( query = 'aniMetaMirrorTrans_AttrT' )
        mirror_r = mc.optionVar( query = 'aniMetaMirrorTrans_AttrR' )
        axis = mc.optionVar( query = 'aniMetaMirrorTrans_Axis' ) + 1

        mc.radioButtonGrp( self.mode_ctrl, edit = True, select = mode )
        mc.checkBoxGrp( self.attr_ctrl, edit = True, value1 = mirror_t )
        mc.checkBoxGrp( self.attr_ctrl, edit = True, value2 = mirror_r )
        mc.radioButtonGrp( self.axis_ctrl, edit = True, select = axis )

    def reset_settings( self, *args ):

        mc.radioButtonGrp( self.mode_ctrl, edit = True, select = 1 )

        mc.checkBoxGrp( self.attr_ctrl, edit = True, value1 = 1 )

        mc.checkBoxGrp( self.attr_ctrl, edit = True, value2 = 1 )

        mc.radioButtonGrp( self.axis_ctrl, edit = True, select = 1 )

        self.save_settings()

    def mirror( self, *args ):

        sel = mc.ls( sl = True )

        if len( sel ) == 2:
            Rig().mirror_handle()
        else:
            print("aniMeta: Please select two transforms, a source and then a destination.")


# Transform Mirror UI
#
######################################################################################

######################################################################################
#
# Rig

class Rig( Transform ):

    rigCustomCtrls = { }

    def __init__(self):
        super( Rig, self ).__init__()
        self.rootNode = None

    def build_joints( self, skeleton = None, char = None ):
        '''
        Builds a joint hierarchy based on a dictionary containing the necessary info.
        :param skeleton: the dictionary
        :return:
        '''

        if skeleton is None:
            skeleton = { }

        joints = skeleton[ 'Skeleton' ][ 'Joints' ]

        new_joints = { }

        rootNode = None

        # Create Joints
        for joint in joints.keys():
            newJoint = mc.createNode( joints[ joint ][ 'nodeType' ], name = joint, ss = True )
            new_joints[ joint ] = self.get_path( newJoint )

        # Parenting
        for joint in joints.keys():
            if 'parent' in skeleton[ 'Skeleton' ][ 'Joints' ][ joint ]:
                parent = skeleton[ 'Skeleton' ][ 'Joints' ][ joint ][ 'parent' ]

                if parent in new_joints:
                    parent = new_joints[ parent ]

                self.parent_joints( new_joints[ joint ], parent, char )
            else:
                print( 'parent is not in dict.' )
                rootNode = joint
        # Set Attributes
        for joint in joints.keys():

            for attr in skeleton[ 'Skeleton' ][ 'Joints' ][ joint ]:

                if attr != 'parent' and attr != 'nodeType':
                    try:
                        value = skeleton[ 'Skeleton' ][ 'Joints' ][ joint ][ attr ]

                        if attr == 'side':
                            value = self.hik_side.index( value )
                        elif attr == 'type':
                            value = self.hik_type.index( value )

                        mc.setAttr( new_joints[ joint ].fullPathName() + '.' + attr, value )
                    except:
                        mc.warning( 'Import skeleton: There is a problem setting attribute ', joint + '.' + attr )
                        pass

        # rename in case names got changed during creation due to existing objects with same name
        for joint in joints.keys():
            try:
                joint = self.short_name( joint )
                mc.rename( new_joints[ joint ].fullPathName(), joint )
            except:
                pass

        if rootNode is not None:
            return new_joints[ rootNode ].fullPathName()
        else:
            return True

    def build_skeleton( self, skeleton = None, char = None ):
        '''
        Builds a joint hierarchy based on a dictionary containing the necessary info.
        :param skeleton: the dictionary
        :return:
        '''

        if skeleton is None:
            skeleton = { }

        if len( skeleton ):
            joints = skeleton[ 'Skeleton' ][ 'Joints' ]

            new_joints = { }

            rootNode = None

            # Create Joints
            for joint in joints.keys():
                newJoint = mc.createNode( joints[ joint ][ 'nodeType' ], name = joint, ss = True )
                new_joints[ joint ] = self.get_path( newJoint )

            # Parenting
            for joint in joints.keys():
                if 'parent' in skeleton[ 'Skeleton' ][ 'Joints' ][ joint ]:
                    parent = skeleton[ 'Skeleton' ][ 'Joints' ][ joint ][ 'parent' ]

                    if parent in new_joints:
                        parent = new_joints[ parent ]

                    self.parent_skeleton( new_joints[ joint ], parent, char )
                else:
                    print( 'parent is not in dict.' )
                    rootNode = joint
            # Set Attributes
            for joint in joints.keys():

                for attr in skeleton[ 'Skeleton' ][ 'Joints' ][ joint ]:

                    if attr != 'parent' and attr != 'nodeType':
                        try:
                            value = skeleton[ 'Skeleton' ][ 'Joints' ][ joint ][ attr ]

                            if attr == 'side':
                                value = self.hik_side.index( value )
                            elif attr == 'type':
                                value = self.hik_type.index( value )

                            mc.setAttr( new_joints[ joint ].fullPathName() + '.' + attr, value )
                        except:
                            mc.warning( 'Import skeleton: There is a problem setting attribute ', joint + '.' + attr )
                            pass

            if char is None:
                self.get_active_char()

            # Get the extra group to save the extra trasnforms in there and not in the joint hierarchy
            proxy_grp = self.find_node( char, 'Proxy_Grp')

            if not proxy_grp:
                offset_grp = self.find_node( char, 'Offset_Grp')
                guides_aux_grp = mc.createNode( 'transform', name='Proxy_Grp', parent=offset_grp, ss=True )

            # rename in case names got changed during creation due to existing objects with same name
            for joint in joints.keys():
                try:
                    joint = self.short_name( joint )
                    mc.rename( new_joints[ joint ].fullPathName(), joint )
                except:
                    pass

                if mc.nodeType( new_joints[ joint ].fullPathName() ) == 'transform':
                    mc.parent( new_joints[ joint ].fullPathName(), guides_aux_grp )

            if rootNode is not None:
                return new_joints[ rootNode ].fullPathName()
            else:
                return True
        else:
            return None

    def check_attr(self, node, attrName ):
        if not mc.attributeQuery( attrName, node=node, exists=True ):
            mc.addAttr( node, ln=attrName )
            mc.setAttr( node + '.' + attrName, k=1 )


    def connect_multi( self, sourceNode1=None, sourceAttrs1=[], sourceNode2=None, sourceAttrs2=[], node=None, attrs=[]):

        m = mc.createNode(
            'multiplyDivide',
            name = self.short_name( node ) + '_' + attrs[0] + '_gs_multi',
            ss = True
        )
        # Should have more sanity checks, for now it is just this...
        try:
            mc.setAttr( node + '.' + attrs[0], l = 0 )

            self.check_attr( sourceNode1, sourceAttrs1[0])
            self.check_attr( sourceNode2, sourceAttrs2[0])

            mc.connectAttr( sourceNode1 + '.' + sourceAttrs1[0], m + '.input1X' )
            mc.connectAttr( sourceNode2 + '.' + sourceAttrs2[0], m + '.input2X' )
            mc.connectAttr( m + '.outputX', node + '.' + attrs[0], f=True )

            if len ( sourceAttrs1 ) == 3:
                self.check_attr(sourceNode1, sourceAttrs1[1])
                self.check_attr(sourceNode2, sourceAttrs2[1])
                self.check_attr(sourceNode1, sourceAttrs1[2])
                self.check_attr(sourceNode2, sourceAttrs2[2])

                mc.connectAttr( sourceNode1 + '.' + sourceAttrs1[1], m + '.input1Y' )
                mc.connectAttr( sourceNode1 + '.' + sourceAttrs1[2], m + '.input1Z' )

                mc.connectAttr( sourceNode2 + '.' + sourceAttrs2[1], m + '.input2Y' )
                mc.connectAttr( sourceNode2 + '.' + sourceAttrs2[2], m + '.input2Z' )

                mc.connectAttr( m + '.outputY', node + '.' + attrs[1], f=True )
                mc.connectAttr( m + '.outputZ', node + '.' + attrs[2], f=True )

                mc.setAttr( node + '.' + attrs[1], l = 0 )
                mc.setAttr( node + '.' + attrs[2], l = 0 )
        except:
            mc.warning('aniMeta: Can not connect ' + sourceNode1+'.'+sourceAttrs1 + ' to ', sourceNode2+'.'+sourceAttrs2 )
            pass

    def get_pose( self, matrix_as_list=False, handle_mode=1 ):

        char = self.get_active_char()

        #handleMode = 1

        if char is not None:

            if handle_mode == 1:
                handles = Rig().get_char_handles( char, { 'Type': kHandle, 'Side': kAll } )
            else:
                handles = mc.ls(sl=True)
            data = {}

            # This needs to work with namespaces and references
            for s in handles:
                node_data = {}

                attrs = mc.listAttr(s, keyable=True)

                for attr in attrs:
                    try:
                        node_data[attr] = round( mc.getAttr(s + '.' + attr), 4 )
                    except:
                        pass

                world_matrix = self.get_matrix( s, space=kWorld )

                if world_matrix is not None:
                    if matrix_as_list == True:
                        node_data[ 'world_matrix' ] = self.matrix_to_list( world_matrix )
                    else:
                        node_data['world_matrix'] = world_matrix

                if ':' in s:
                    buff = s.split(':')
                    name = buff[len(buff)-1]
                else:
                    name=s

                if '|' in name:
                    buff = name.split('|')
                    name = buff[len(buff)-1]

                data[name] = node_data


            sceneDict = self.get_scene_info()

            poseDict = { }

            poseDict[ 'aniMeta' ] = [ { 'info': sceneDict, 'data_type': 'aniMetaPose' }, { 'data': data } ]

            return poseDict

    def delete_custom_control(self, *args, **kwargs):
        sel = []

        if len(kwargs):

            for key, value in kwargs.items():
                sel.append( value['Constraint'] )

        else:
            sel = mc.ls( sl=True, l=True ) or []

        if len (sel) > 0:

            for ctrl in sel:
                # Get the metadata
                metaData = self.get_metaData( ctrl )
                # Make sure this is a custom handle
                if 'Custom' in metaData:
                    # Find the parent
                    parent = mc.listRelatives( ctrl, parent=True, pa=True )
                    if parent:
                        try:
                            # delete it
                            mc.delete( parent )
                        except:
                            mc.warning( 'aniMeta: Can not delete node' + parent )


    def create_custom_control(self, *args, **kwargs):

        sel = []

        if len(kwargs):

            for key, value in kwargs.items():
                sel.append( value['Constraint'] )

        else:
            sel = mc.ls( sl=True, l=True, typ='joint' ) or []

        if len (sel) > 0:
            ctrls = []

            rootNode = self.get_active_char()

            if not rootNode:
                mc.confirmDialog(
                    m='No character selected. Please select one from the Character Editor.',
                    t='Create Custom Control'
                )
                return None

            rig_grp = self.find_node( rootNode, 'Rig_Grp')

            ctrl_grp = self.find_node( rootNode, 'Custom_Ctrl_Grp')

            if ctrl_grp is None:
                ctrl_grp = mc.createNode('transform', name='Custom_Ctrl_Grp', parent=rig_grp, ss=True)

            ctrlDict = {}
            ctrlDict['character'] = rootNode
            ctrlDict['globalScale'] = True
            ctrlDict['shapeType'] = self.kCube
            ctrlDict['green'] = 1
            ctrlDict['width'] = 6
            ctrlDict['height'] = 6
            ctrlDict['depth'] = 6
            ctrlDict['parent'] = ctrl_grp
            ctrlDict['constraint'] = self.kParent

            data = {}
            data['Type']   = kHandle
            data['Side']   = kAll
            data['Custom'] = True

            for s in sel:
                parent = mc.listRelatives( s, p=True, pa=True )[0]
                s_short = self.short_name(s)
                if 'Jnt' in s_short:
                    ctrlDict['name'] = s_short.replace( 'Jnt', 'Ctrl' )
                else:
                    ctrlDict['name'] = s_short + 'Ctrl'

                ctrlDict['matchTransform'] = s
                ctrlDict['constraintNode'] = s

                ctrl = self.create_handle(**ctrlDict)
                ctrl_parent = mc.listRelatives( ctrl, p=True, pa=True )[0]

                self.set_metaData( ctrl.fullPathName(), data)

                for a in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
                    mc.setAttr( ctrl.fullPathName() + '.' + a, l=False)

                mc.parentConstraint( parent, ctrl_parent, mo=True )

                ctrls.append( ctrl )

            return ctrls
        else:
            return None

    def create_handle(self, **kwargs):
        name = 'Default_Ctrl'
        width = 0
        height = 0
        depth = 0
        size = ( 1, 1, 1 )
        color = ( 1, 1, 0 )
        alpha = 0.15
        radius = 10
        thickness = 1
        createGrp = True
        createBlendGrp = False          # Extra group to dial in mocap
        shapeType = self.kCube
        parent = None
        matchTransform = None
        constraint = None
        constraintNode = None
        maintainOffset = True
        offset = (0, 0, 0)
        rotate = (0, 0, 0)
        offsetMatrix = om.MMatrix()
        charRoot = None
        globalScale = False
        aimVec = [0,0,1]
        upVec = [0,1,0]
        gs = 'globalCtrlScale'
        scale = 1.0
        rotateOrder = kXYZ
        showRotateOrder = False

        if 'name' in kwargs:
            name = kwargs['name']
        if 'width' in kwargs:
            width = kwargs['width']
        if 'height' in kwargs:
            height = kwargs['height']
        if 'depth' in kwargs:
            depth = kwargs['depth']
        if 'size' in kwargs:
            size = kwargs['size']
        if 'red' in kwargs:
            red = kwargs['red']
        if 'green' in kwargs:
            green = kwargs['green']
        if 'blue' in kwargs:
            blue = kwargs['blue']
        if 'alpha' in kwargs:
            alpha = kwargs['alpha']
        if 'radius' in kwargs:
            radius = kwargs['radius']
        if 'thickness' in kwargs:
            thickness = kwargs['thickness']
        if 'createGrp' in kwargs:
            createGrp = kwargs['createGrp']
        if 'createBlendGrp' in kwargs:
            createBlendGrp = kwargs['createBlendGrp']
        if 'shapeType' in kwargs:
            shapeType = kwargs['shapeType']
        if 'matchTransform' in kwargs:
            matchTransform = kwargs['matchTransform']
        if 'parent' in kwargs:
            parent = kwargs['parent']
        if 'constraint' in kwargs:
            constraint = kwargs['constraint']
        if 'constraintNode' in kwargs:
            constraintNode = kwargs['constraintNode']
        if 'maintainOffset' in kwargs:
            maintainOffset = kwargs['maintainOffset']
        if 'offset' in kwargs:
            offset = kwargs['offset']
        if 'rotate' in kwargs:
            rotate = kwargs['rotate']
        if 'offsetMatrix' in kwargs:
            offsetMatrix = kwargs['offsetMatrix']
        if 'character' in kwargs:
            charRoot = kwargs[ 'character' ]
        if 'globalScale' in kwargs:
            globalScale = kwargs[ 'character' ]
        if 'aimVec' in kwargs:
            aimVec = kwargs[ 'aimVec' ]
        if 'upVec' in kwargs:
            upVec = kwargs[ 'upVec' ]
        if 'scale' in kwargs:
            scale = kwargs[ 'scale' ]
        if 'rotateOrder' in kwargs:
            rotateOrder = kwargs[ 'rotateOrder' ]
        if 'showRotateOrder' in kwargs:
            showRotateOrder = kwargs[ 'showRotateOrder' ]
        if 'color' in kwargs:
            color = kwargs['color']

        name = self.short_name( name )

        def check_node( node, type_name, charRoot ):

            out_node = None

            if isinstance( node, om.MDagPath ):
                return node

            if  isinstance( node, str ) :
                out_node = self.find_node( charRoot, node )

                if out_node is not None:
                    out_node = self.get_path( out_node )
                    if out_node is not None:
                        return out_node
                else:
                    print(mc.ls(node))
            return out_node

        parent         = check_node( parent,         'parent'        , charRoot )
        matchTransform = check_node( matchTransform, 'matchTransform', charRoot )
        constraintNode = check_node( constraintNode, 'constraintNode', charRoot )

        if width:
            size = (width, height, depth )

        if shapeType == self.kCube:

            shape     = mc.polyCube(w=size[0], h=size[1], d=size[2], ch=1 )
            shape[1]  = mc.rename( shape[1], name+'_Cube')
            ctrl_path = self.get_path( shape[0] )

            mc.addAttr(ctrl_path.fullPathName(), ln='controlSizeX', dv=size[0])
            mc.addAttr(ctrl_path.fullPathName(), ln='controlSizeY', dv=size[1])
            mc.addAttr(ctrl_path.fullPathName(), ln='controlSizeZ', dv=size[2])

            if not globalScale:
                mc.connectAttr(ctrl_path.fullPathName() + '.controlSizeX', shape[1] + '.width')
                mc.connectAttr(ctrl_path.fullPathName() + '.controlSizeY', shape[1] + '.height')
                mc.connectAttr(ctrl_path.fullPathName() + '.controlSizeZ', shape[1] + '.depth')
            else:
                self.connect_multi(
                    charRoot,
                    [ gs, gs, gs ],
                    shape[ 0 ],
                    [ 'controlSizeX', 'controlSizeY', 'controlSizeZ' ],
                    shape[1],
                    [ 'width', 'height', 'depth' ]
                )
        elif shapeType == self.kSphere:

            shape = mc.polyCube(w=radius, h=radius, d=radius, ch=1, name=name+'_Cube')
            ctrl_path = self.get_path( shape[0] )
            shape[1] = mc.rename( shape[1], name+'_Cube')
            smooth = mc.polySmooth( ctrl_path.fullPathName() )
            smooth[0] = mc.rename( smooth[0], name+'_Smooth')

            mc.addAttr( ctrl_path.fullPathName(), ln='controlSize', dv=radius*2)
            mc.addAttr( ctrl_path.fullPathName(), ln='controlSmoothing', at='short', min=0, max=2, dv=2 )

            if not globalScale:
                mc.connectAttr( ctrl_path.fullPathName() + '.controlSize', shape[1] + '.width' )
                mc.connectAttr( ctrl_path.fullPathName() + '.controlSize', shape[1] + '.height' )
                mc.connectAttr( ctrl_path.fullPathName() + '.controlSize', shape[1] + '.depth' )
                mc.connectAttr( ctrl_path.fullPathName() + '.controlSmoothing', smooth[0] + '.divisions' )
            else:
                try:
                    self.connect_multi(
                        charRoot,
                        [ gs, gs, gs ],
                        shape[ 0 ],
                        [ 'controlSize', 'controlSize', 'controlSize' ],
                        shape[1],
                        [ 'width', 'height', 'depth' ]
                    )
                except:
                    pass

        elif shapeType == self.kPipe:

            axis = [0,1,0]
            offset = (0,0,radius * 0.3 * scale)
            if mc.upAxis(query=True, axis=True) == 'z':
                axis = [0,0,1]
                offset = (0, -radius * 0.3 * scale, 0)

            shape = mc.polyPipe(r=radius, h=height, t=thickness, sa=20, sh=1, sc=0, ax=axis, rcp=False, ch=True )
            ctrl_path = self.get_path( shape[0] )

            shape[1] = mc.rename( shape[1], name+'_Pipe')
            mc.xform( ctrl_path.fullPathName() + '.vtx[15]', t=offset, r=True, ws=True)
            mc.xform( ctrl_path.fullPathName() + '.vtx[35]', t=offset, r=True, ws=True)
            mc.xform( ctrl_path.fullPathName() + '.vtx[55]', t=offset, r=True, ws=True)
            mc.xform( ctrl_path.fullPathName() + '.vtx[75]', t=offset, r=True, ws=True)

            mc.addAttr( ctrl_path.fullPathName(), ln='controlSize', dv=radius*2)

            if not globalScale:
                # to do ...
                pass
            else:
                self.connect_multi(
                    charRoot,
                    [ gs ],
                    shape[ 0 ],
                    [ 'controlSize' ],
                    shape[1],
                    [ 'radius' ]
                )

        mc.addAttr(ctrl_path.fullPathName(), ln='controlOffset', at='compound', numberOfChildren=3)
        mc.addAttr(ctrl_path.fullPathName(), ln='controlOffsetX', parent='controlOffset', at='float')
        mc.addAttr(ctrl_path.fullPathName(), ln='controlOffsetY', parent='controlOffset', at='float')
        mc.addAttr(ctrl_path.fullPathName(), ln='controlOffsetZ', parent='controlOffset', at='float')

        if rotate[0] != 0 or rotate[1] != 0 or rotate[2] != 0:
            count = mc.polyEvaluate(ctrl_path.fullPathName(), v=True)
            shapeComp = ctrl_path.fullPathName() + '.vtx[0:' + str(count - 1) + ']'
            mc.rotate(rotate[0], rotate[1], rotate[2], shapeComp, r=True, os=True)

        if offset[0] != 0 or offset[1] != 0 or offset[2] != 0:
            count = mc.polyEvaluate(ctrl_path.fullPathName(), v=True)
            shapeComp = ctrl_path.fullPathName() + '.vtx[0:' + str(count - 1) + ']'
            mc.move(offset[0], offset[1], offset[2], shapeComp, r=True, os=True)

        mc.polyColorPerVertex(ctrl_path.fullPathName(), rgb=color, alpha=alpha)

        cluster = mc.deformer( ctrl_path.fullPathName(), type='cluster', name='aniMetaCluster')
        compMatrix = mc.createNode('composeMatrix', ss=True, name=name+'HandleOffsetMatrix')

        mc.connectAttr( ctrl_path.fullPathName()+'.controlOffset', compMatrix + '.inputTranslate')
        mc.connectAttr( compMatrix+'.outputMatrix', cluster[0] + '.matrix')

        for node in mc.listHistory( ctrl_path.fullPathName()):
            if mc.nodeType( node ) == 'polyColorPerVertex':
                mc.rename( node, name+'_Color')

        mc.setAttr(ctrl_path.fullPathName() + '.displayColors', True)
        mc.setAttr(ctrl_path.fullPathName() + '.backfaceCulling', 3)
        mc.setAttr(ctrl_path.fullPathName() + '.allowTopologyMod', 0)
        mc.setAttr(ctrl_path.fullPathName() + '.smoothLevel', 0)

        grp = None
        blend_grp = None

        if createGrp:
            if createBlendGrp:
                grp = mc.createNode('transform', name=name + '_Grp', ss=True)
                blend_grp = mc.createNode('transform', name=name + '_Blnd_Grp', parent=grp, ss=True)
                mc.parent( ctrl_path.fullPathName(), blend_grp)
            else:
                grp = mc.createNode('transform', name=name + '_Grp', ss=True)
                mc.parent( ctrl_path.fullPathName(), grp)

        mc.rename( ctrl_path.fullPathName(), name)

        if matchTransform is not None:

            m = offsetMatrix * self.get_matrix( matchTransform, kWorld )

            if createGrp:
                self.set_matrix( grp, m )
        if showRotateOrder == True:
            mc.setAttr( ctrl_path.fullPathName() + '.rotateOrder', k=True)

        mc.setAttr( ctrl_path.fullPathName() + '.rotateOrder', rotateOrder)

        # Turn off rendering attributes
        for attr in [ "castsShadows",  "receiveShadows", "motionBlur", "primaryVisibility",
                      "smoothShading", "visibleInReflections", "visibleInRefractions", "doubleSided" ]:
            mc.setAttr( ctrl_path.fullPathName() + '.' + attr, False )

        if parent is not None:
            grp = mc.parent( grp, parent.fullPathName() )[0]

        target = constraintNode

        # Is this good? Not Really in the case of Hips UpVector Control
        if target is None:
            target = matchTransform

        # If a constraint node is specified but not the constraint type, use parentConstraint as default
        if constraintNode is not None:
            constraint = self.kParent

        if constraint is not None and target is not None:

            if constraint == self.kParent:
                try:
                    mc.parentConstraint( ctrl_path.fullPathName(), target.fullPathName(), mo=maintainOffset)
                except:
                    pass
                
            if constraint == self.kAim:
                mc.aimConstraint( ctrl_path.fullPathName(), target.fullPathName(), mo=maintainOffset, upVector=upVec, aimVector=aimVec)

        mc.select( cl=True )

        return ctrl_path

    def create_joystick_widget_ui(self, *args, **kwargs):

        self.joystick_ui = 'aniMetaJoystickUI'

        if mc.window(self.joystick_ui, exists=True):
            mc.deleteUI(self.joystick_ui)

        mc.window(self.joystick_ui, title='Create Joystick', w=200, h=100, rtf=True)

        mc.rowColumnLayout(numberOfColumns=1, rs=[1, 10], ro=[1, 'top', 10])

        self.joystick_ui_name_ctrl = mc.textFieldGrp(label='Name')

        row2 = mc.rowColumnLayout(numberOfColumns=2, cs=[1, 10])
        mc.rowColumnLayout(row2, e=True, cs=[2, 10])

        mc.button(label='Create', width=120, command=self.create_joystick_widget_doit)
        mc.button(label='Cancel', width=120, command=partial(self.close_joystick_dialog, self.joystick_ui))

        mc.showWindow()

    def close_joystick_dialog(self, *args):

        print( args )

    def create_joystick_widget_doit(self, *args):

        name = mc.textFieldGrp(self.joystick_ui_name_ctrl, q=True, text=True)
        self.create_joystick_widget( name )


    def create_joystick_widget(self, control_name = 'brow_L' ):

        if mc.objExists( control_name ):
            mc.confirmDialog(m='An object with this name exists, please choose a unique name.' )

        grp = mc.createNode ( 'transform', name=control_name+'_grp', ss=True )

        title = mc.textCurves( name=control_name+"Text", ch=1, f="Courier", t=control_name.replace('_', ' ' ))[0]

        mc.setAttr( title + '.t', -1, -1.5, 0 )
        mc.setAttr( title + '.s', .5, .5, .5 )
        mc.setAttr( title + '.overrideEnabled', True )
        mc.setAttr( title + '.overrideDisplayType', 1 )
        control = mc.circle( name=control_name, nr=[0,0,1], sw=360, r=0.1, d=3, ut=0, tol=0.01, s=8, ch=False )[0]

        mc.transformLimits( control, etx=(1,1), ety=(1,1), tx=(-1,1), ty=(-1,1))

        for attr in ( 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'v' ):
            mc.setAttr( control + '.' + attr, l=1, k=0 )

        plane = mc.polyPlane( name=control_name+'_Widget', w=2, h=2, sx=1, sy=1, ax=(0,0,1), cuv=1, ch=0 )[0]

        mc.parent( control, plane, title, grp )

        mc.setAttr( plane + '.overrideEnabled', True )
        mc.setAttr( plane + '.overrideDisplayType', 1 )

        prefix = 'joystick'

        source_attr_x = 'translateX'
        source_attr_y = 'translateY'

        for attr in ['NW', 'NE', 'SW', 'SE' ]:
            if not mc.attributeQuery( attr, node = control, exists=True ):
                mc.addAttr( control, ln = attr, keyable=0, min=0, max=1, dv=1, at='double' )

        ###########################################################################################
        # Up

        js_up_unitCon_1 = mc.createNode( 'unitConversion', name=prefix+'Up_unitCon_1', ss=True )
        mc.setAttr( js_up_unitCon_1 + '.conversionFactor', -1 )
        mc.connectAttr( control + '.' + source_attr_x, js_up_unitCon_1 + '.input' )

        js_up_add_1 =  mc.createNode( 'plusMinusAverage', name=prefix+'Up_add_1', ss=True )
        mc.setAttr( js_up_add_1 + '.input1D[0]', 1 )
        mc.connectAttr( control + '.' + source_attr_x, js_up_add_1 + '.input1D[1]' )

        js_up_add_2 =  mc.createNode( 'plusMinusAverage', name=prefix+'Up_add_2', ss=True )
        mc.setAttr( js_up_add_2 + '.input1D[0]', 1 )
        mc.connectAttr( js_up_unitCon_1 + '.output', js_up_add_2 + '.input1D[1]' )

        js_up_cond_1 = mc.createNode( 'condition', name=prefix+'Up_cond_1', ss=True )
        mc.setAttr( js_up_cond_1 + '.operation', 2 )
        mc.setAttr( js_up_cond_1 + '.colorIfTrueR', 1 )
        mc.setAttr( js_up_cond_1 + '.colorIfFalseG', 1 )
        mc.connectAttr( js_up_add_1 + '.output1D', js_up_cond_1 + '.colorIfFalseR' )
        mc.connectAttr( js_up_add_2 + '.output1D', js_up_cond_1 + '.colorIfTrueG' )
        mc.connectAttr( control + '.translateX', js_up_cond_1 + '.firstTerm' )

        js_up_multi_1 = mc.createNode( 'multiplyDivide', name=prefix+'Up_multi_1', ss=True )
        mc.connectAttr( control + '.translateY', js_up_multi_1 + '.input1X' )
        mc.connectAttr( control + '.translateY', js_up_multi_1 + '.input1Y' )
        mc.connectAttr( js_up_cond_1 + '.outColorR', js_up_multi_1 + '.input2X' )
        mc.connectAttr( js_up_cond_1 + '.outColorG', js_up_multi_1 + '.input2Y' )

        js_up_clamp_1 = mc.createNode( 'clamp', name=prefix+'Up_clamp_1', ss=True )
        mc.setAttr( js_up_clamp_1 + '.minR', 0 )
        mc.setAttr( js_up_clamp_1 + '.minG', 0 )
        mc.setAttr( js_up_clamp_1 + '.maxR', 1 )
        mc.setAttr( js_up_clamp_1 + '.maxG', 1 )
        mc.connectAttr( js_up_multi_1 + '.outputX', js_up_clamp_1 + '.inputR' )
        mc.connectAttr( js_up_multi_1 + '.outputY', js_up_clamp_1 + '.inputG' )

        mc.connectAttr( js_up_clamp_1 + '.outputR', control + '.NW' )
        mc.connectAttr( js_up_clamp_1 + '.outputG', control + '.NE' )

        # Up
        ###########################################################################################

        ###########################################################################################
        # Lo
        js_lo_unitCon_1 = mc.createNode( 'unitConversion', name=prefix+'Lo_unitCon_1', ss=True )
        mc.setAttr( js_lo_unitCon_1 + '.conversionFactor', -1 )
        mc.connectAttr( control + '.' + source_attr_x, js_lo_unitCon_1 + '.input' )

        js_lo_add_1 =  mc.createNode( 'plusMinusAverage', name=prefix+'Lo_add_1', ss=True )
        mc.setAttr( js_lo_add_1 + '.input1D[0]', 1 )
        mc.connectAttr( control + '.' + source_attr_x, js_lo_add_1 + '.input1D[1]' )

        js_lo_add_2 =  mc.createNode( 'plusMinusAverage', name=prefix+'Lo_add_2', ss=True )
        mc.setAttr( js_lo_add_2 + '.input1D[0]', 1 )
        mc.connectAttr( js_lo_unitCon_1 + '.output', js_lo_add_2 + '.input1D[1]' )

        js_lo_cond_1 = mc.createNode( 'condition', name=prefix+'Lo_cond_1', ss=True )
        mc.setAttr( js_lo_cond_1 + '.operation', 2 )
        mc.setAttr( js_lo_cond_1 + '.colorIfTrueR', 1 )
        mc.setAttr( js_lo_cond_1 + '.colorIfFalseG', 1 )
        mc.connectAttr( js_lo_add_1 + '.output1D', js_lo_cond_1 + '.colorIfFalseR' )
        mc.connectAttr( js_lo_add_2 + '.output1D', js_lo_cond_1 + '.colorIfTrueG' )
        mc.connectAttr( control + '.translateX', js_lo_cond_1 + '.firstTerm' )

        js_lo_multi_2 = mc.createNode( 'multiplyDivide', name=prefix+'Lo_multi_2', ss=True )
        mc.setAttr( js_lo_multi_2 + '.input2X', -1 )
        mc.setAttr( js_lo_multi_2 + '.input2Y', -1 )
        mc.connectAttr( control + '.translateY', js_lo_multi_2 + '.input1X' )
        mc.connectAttr( control + '.translateY', js_lo_multi_2 + '.input1Y' )

        js_lo_multi_1 = mc.createNode( 'multiplyDivide', name=prefix+'Lo_multi_1', ss=True )
        mc.connectAttr( js_lo_multi_2 + '.outputX', js_lo_multi_1 + '.input1X' )
        mc.connectAttr( js_lo_multi_2 + '.outputY', js_lo_multi_1 + '.input1Y' )
        mc.connectAttr( js_lo_cond_1 + '.outColorR', js_lo_multi_1 + '.input2X' )
        mc.connectAttr( js_lo_cond_1 + '.outColorG', js_lo_multi_1 + '.input2Y' )

        js_lo_clamp_1 = mc.createNode( 'clamp', name=prefix+'Lo_clamp_1', ss=True )
        mc.setAttr( js_lo_clamp_1 + '.minR', 0 )
        mc.setAttr( js_lo_clamp_1 + '.minG', 0 )
        mc.setAttr( js_lo_clamp_1 + '.maxR', 1 )
        mc.setAttr( js_lo_clamp_1 + '.maxG', 1 )
        mc.connectAttr( js_lo_multi_1 + '.outputX', js_lo_clamp_1 + '.inputR' )
        mc.connectAttr( js_lo_multi_1 + '.outputY', js_lo_clamp_1 + '.inputG' )

        mc.connectAttr( js_lo_clamp_1 + '.outputR', control + '.SW' )
        mc.connectAttr( js_lo_clamp_1 + '.outputG', control + '.SE' )

        mc.select( grp )

        return control, grp

    def create_nul(self, *args ):

        sel = []
        if len(args):
            if args[0] is not False:
                sel=args
        if len(sel) == 0:
            sel = mc.ls(sl=True, l=True) or []
        nuls = []
        if len(sel) > 0:
            for obj in sel:
                m = self.get_matrix( obj, space= kWorld )
                ro = mc.getAttr( obj + '.rotateOrder')
                name =  self.short_name(obj)
                parent = mc.listRelatives( obj, p=True, pa=True )
                if parent:
                    parent=parent[0]

                nul = mc.createNode('transform', name=name + '_nul', ss=True, parent=parent)
                mc.setAttr( nul + '.rotateOrder', ro )
                self.set_matrix(nul, m, space= kWorld )
                mc.parent(obj, nul)
                nuls.append(nul)
        else:
            mc.warning( 'aniMeta: No nodes to create nuls for.')
        return nuls

    def create_pair_blend( self, node, inNode, mode, weight ):

        pair = mc.createNode( 'pairBlend', ss = True, name = self.short_name( node ) + '_PB' )
        mc.setAttr( pair + '.weight', weight )

        if mode == kPairBlendRotate or mode == kPairBlend:
            r = mc.getAttr( node + '.r' )
            mc.setAttr( pair + '.inRotate2', r[ 0 ][ 0 ], r[ 0 ][ 1 ], r[ 0 ][ 2 ] )
            mc.connectAttr( inNode + '.r', pair + '.inRotate1', f = True )
            mc.setAttr( pair + '.rotInterpolation', 1 )
            mc.connectAttr( pair + '.outRotate', node + '.rotate', f = True )

        if mode == kPairBlendTranslate or mode == kPairBlend:
            mc.connectAttr( inNode + '.t', pair + '.inTranslate1', f = True )
            mc.connectAttr( pair + '.outTranslate', node + '.translate', f = True )

        return pair

    def create_space_switch(self, ctrl, cnst_node='Head_Ctr_Ctrl', attrName='world', invert=False ):

        char = self.get_active_char()

        ctrl_short = self.short_name( ctrl )
        cnst_short = self.short_name( cnst_node )

        node = self.find_node(char, ctrl_short)  # find the node
        ctrl_parent = mc.listRelatives(node, p=True, pa=True)

        if ctrl_parent is not None:
            ctrl_parent = ctrl_parent[0]

            cnst_grp = mc.createNode(   'transform',
                                       parent=ctrl_parent,
                                       ss=True,
                                       name=ctrl_short + '_Cnst_Grp')
            blend_grp = mc.createNode('transform',
                                       parent=ctrl_parent,
                                       ss=True,
                                       name=ctrl_short + '_Blnd_Grp')

            # Create Pairblend so we can dial the mocap effect in or out
            pb = self.create_pair_blend(blend_grp,
                                        cnst_grp,
                                        kPairBlend,
                                        False)
            # Add Mocap Attribute
            if not mc.attributeQuery( attrName, node=node, exists=True ):
                mc.addAttr( node, ln=attrName, min=0, max=1 )
                mc.setAttr( node + '.' + attrName, k=1 )

            if invert:
                rev_name=self.short_name( ctrl )
                rev = mc.createNode( 'reverse', ss=True, name=rev_name + '_Inv')
                mc.connectAttr( node + '.' + attrName, rev + '.ix' )
                mc.connectAttr( rev + '.ox', pb + '.weight' )
            else:
                mc.connectAttr( node + '.' + attrName, pb + '.weight' )

            mc.parent( node, blend_grp)

            node = self.find_node(char, cnst_node )  # find the node

            mc.parentConstraint(node, cnst_grp, mo=True)

    def create_multi_space_switch(self, ctrl, cnst_nodes, attrName='space', attrNameList=['Main']):

        char        = self.get_active_char()
        ctrl_short  = self.short_name( ctrl )
        #ctrl_path   = self.find_node(char, ctrl_short)
        ctrl_parent = mc.listRelatives( ctrl.fullPathName(), p=True, pa=True)

        cnst_nodes_long = []

        for cnst in cnst_nodes:
            cnst_nodes_long.append( cnst.fullPathName() )


        if ctrl_parent is not None:
            ctrl_parent = ctrl_parent[0]
            cnst_grp = self.create_nul(  ctrl_parent )[0]

            # Path changed so we need to refind the node
            #ctrl_path   = self.find_node(char, ctrl_short)

            # Match the constraint group transform to the control
            enum_string = ''
            for attr in attrNameList:
                enum_string += attr + ':'

            # Create the space-switch attribute
            mc.addAttr( ctrl.fullPathName(), longName=attrName, at='enum', en=enum_string )
            mc.setAttr( ctrl.fullPathName() + '.' + attrName, k=True)

            # Create the control
            cnst = mc.parentConstraint( cnst_nodes_long, cnst_grp, mo=True)[0]

            wl = mc.parentConstraint(cnst, q=True, wal=True)
            ctrl = ctrl.fullPathName()+ '.' + attrName

            # Connect the space switch attribute to the parentConstraint weights with condition nodes
            index = 0
            for w in wl:
                c = mc.createNode( 'condition', name=ctrl_short + '_cond' + str(index), ss=True )
                mc.connectAttr( ctrl, c + '.firstTerm' )
                mc.setAttr( c + '.secondTerm', index )
                # Check if first and second term are equal
                mc.setAttr( c + '.operation', 0 )
                mc.setAttr( c + '.colorIfTrueR', 1 )
                mc.setAttr( c + '.colorIfFalseR', 0 )
                mc.connectAttr( c + '.outColorR', cnst + '.' + w )
                index += 1

    def create_sym_con_hier(self, *args):

        sel = mc.ls( sl=True )

        if len ( sel ) == 1:

            joints = mc.listRelatives( sel[0], typ='joint', ad=True, pa=True )

            for joint in joints:

                short = self.short_name( joint )

                if 'Lft' in short:

                    joint_r = self.find_node( sel[0], short.replace('Lft', 'Rgt'))

                    if joint_r:
                        self.create_sym_constraint( joint, joint_r )

    def create_sym_con(self, *args):

        sel = mc.ls(sl=True)

        if len( sel ) == 2:
            return self.create_sym_constraint( sel[0], sel[1] )

    def create_sym_constraint(self, tgtNode='joint_Lft', cnstNode='joint_Rgt'):

        if tgtNode is None:
            print ('aniMeta: no valid target node for symmetryConstraint specified, aborting.', tgtNode )
            return False

        if cnstNode is None:
            print ('aniMeta: no valid constraint node for symmetryConstraint specified, aborting.')
            return False

        tgtNode = self.get_path( tgtNode )
        cnstNode = self.get_path( cnstNode )

        if tgtNode and cnstNode:
            target     = tgtNode.fullPathName()
            constraint = cnstNode.fullPathName()

            # Check whether there is already a symConstraint
            tgtCon  = mc.listConnections( target + '.translate', d=True, s=False ) or []
            cnstCon = mc.listConnections( constraint + '.translate', s=True, d=False ) or []

            if len( tgtCon ) and len( cnstCon ):
                if tgtCon[0] == cnstCon[0]:
                    return tgtCon[0]

            symNode = mc.createNode('symmetryConstraint', ss=True, name=self.short_name(cnstNode) + '_SymCnst', parent=cnstNode)

            mc.connectAttr( target + '.translate',                   symNode + '.targetTranslate')
            mc.connectAttr( target + '.rotate',                      symNode + '.targetRotate')
            mc.connectAttr( target + '.scale',                       symNode + '.targetScale')
            mc.connectAttr( target + '.rotateOrder',                 symNode + '.targetRotateOrder')
            mc.connectAttr( target + '.worldMatrix[0]',              symNode + '.targetWorldMatrix')
            mc.connectAttr( target + '.parentMatrix[0]',             symNode + '.targetParentMatrix')

            mc.connectAttr( symNode + '.constraintTranslate',        constraint + '.translate')
            mc.connectAttr( symNode + '.constraintRotate',           constraint + '.rotate')
            mc.connectAttr( symNode + '.constraintRotateOrder',      constraint + '.rotateOrder')
            mc.connectAttr( symNode + '.constraintScale',            constraint + '.scale')
            mc.connectAttr( constraint + '.parentInverseMatrix[0]',  symNode + '.constraintInverseParentWorldMatrix')

            if mc.nodeType( tgtNode.fullPathName() ) == 'joint' and mc.nodeType( constraint ) == 'joint':
                mc.connectAttr( target + '.jointOrient',            symNode + '.targetJointOrient')
                mc.connectAttr( symNode + '.constraintJointOrient', constraint + '.jointOrient')

            return symNode

        if not tgtNode :
            mc.warning('Can not find target node: ' + tgtNode)

        if not cnstNode :
            mc.warning('Can not find constrained node: ' + cnstNode)

        return None

    def create_vis_switch(self, node, nodes, attrName):
        '''
        Creates a visbility switch on the specified node.
        :param node: The source node that gets the attribute
        :param nodes: The nodes that get the connection
        :param attrName: The name of the attribute
        '''

        mc.addAttr( node, longName=attrName, at='enum', en='off:on:')
        mc.setAttr( node+'.'+attrName, k=True)

        for i in range( len(nodes)):
            try:
                mc.connectAttr( node + '.' + attrName, nodes[i] + '.v', force=True)
            except:
                pass

    def delete_nodes( self, char, nodes ):

        for node in nodes:
            node = self.find_node( char, node)
            if node is not None:
                mc.delete(node)


    def export_drivenKeys( self, drivenKeys, fileName ):


        drivenKeysData = {}

        anim = Anim()

        for i in range( len(drivenKeys)):

            result = anim.get_anim_curve_data( drivenKeys[i] )
            drivenKeysData[drivenKeys[i]] = result


        data_json = json.dumps( drivenKeysData, indent = 4 )

        with open(fileName, 'w') as file_obj:
            file_obj.write( data_json)


    def export_joints( self, joints, fileName ):

        skeleton = { }

        skeleton[ 'Skeleton' ] = { }
        skeleton[ 'Skeleton' ][ 'Joints' ] = { }

        for joint in joints:

            if mc.nodeType( joint ) == 'joint' or mc.nodeType( joint ) == 'transform':
                jointPath = self.get_path( joint )

                shortPath = jointPath.partialPathName()

                if '|' in shortPath:
                    buff = shortPath.split( '|' )
                    shortPath = buff[ len( buff ) - 1 ]

                if ':' in shortPath:
                    buff = shortPath.split( ':' )
                    shortPath = buff[ len( buff ) - 1 ]

                skeleton[ 'Skeleton' ][ 'Joints' ][ shortPath ] = { }


                dict = { }
                for i in range( len( self.attrs ) ):

                    try:
                        value = round( mc.getAttr( joint + '.' + self.attrs[ i ] ), 4 )

                        if value != self.defaults[ i ]:

                            if self.attrs[ i ] == 'side':
                                dict[ self.attrs[ i ] ] = self.hik_side[ int( value ) ]
                            elif self.attrs[ i ] == 'type':
                                dict[ self.attrs[ i ] ] = self.hik_type[ int( value ) ]
                            else:
                                dict[ self.attrs[ i ] ] = value
                    except:
                        pass
                try:
                    parent = mc.listRelatives( joint, p = True, pa=True )[ 0 ]

                    if ':' in parent:
                        buff = parent.split( ':' )
                        parent = buff[ len( buff ) - 1 ]

                    dict[ 'parent' ] = parent

                except:
                    pass

                opm = mc.getAttr( joint + '.offsetParentMatrix')

                # Check whether there are values on the offsetParentMatrix
                if not self.is_identity( opm ):
                    dict[ 'offsetParentMatrix' ] = opm

                dict[ 'nodeType' ] = mc.nodeType( joint )

            if len( dict ) > 0:
                skeleton[ 'Skeleton' ][ 'Joints' ][ shortPath ] = dict

        data_json = json.dumps( skeleton, indent = 1 )

        with open( fileName, 'w') as file_obj:
            file_obj.write( data_json )

    def is_identity( self, matrix ):
        identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        for i in range( 16 ):
            if matrix[i] != identity[i]:
                return False
        return True

    def export_drivenKeys_ui( self, *args, **kwargs ):
        jnts = mc.ls( sl = True ) or [ ]

        if len( jnts ) > 0:
            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Save',
                                     cap = 'Save Driven Keys' )

            fileName = result[ 0 ]

            self.export_drivenKeys( jnts, fileName )

            print( 'Driven Keys exported to file ', fileName )

    def export_joints_ui( self, *args, **kwargs ):
        jnts = mc.ls( sl = True ) or [ ]

        if len( jnts ) > 0:
            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Save',
                                     cap = 'Save Skeleton' )

            fileName = result[ 0 ]

            self.export_joints( jnts, fileName )

            print( 'Skeleton exported to file ', fileName )

    def get_attributes( self, node, getAnimKeys = True ):
        if mc.objExists( node ) == False:
            mc.warning( 'aniMeta get_attributes: object does not exist ', node )
            return None

        attrs = mc.listAttr( node, k = True ) or [ ]

        if mc.nodeType( node ) in [ 'transform', 'joint' ]:
            attrs.append( 'rotateOrder' )

        dict = { }

        if len( attrs ) > 0:

            for attr in attrs:
                attrDict = { }
                status = 0

                attrDict[ 'dataType' ] = mc.attributeQuery( attr, node = node, attributeType = True )

                con = mc.listConnections( node + '.' + attr, s = True, d = False ) or [ ]

                if len( con ) > 0:

                    if mc.nodeType( con ) in curveType:
                        attrDict[ 'input' ] = attrInput[ animCurve ]
                        # Either get the actual keyframe animation
                        if getAnimKeys:
                            attrDict[ 'animCurve' ] = Anim().get_anim_curve_data( con[ 0 ] )
                        # or just the animation node
                        else:
                            attrDict[ 'animCurve' ] = con[ 0 ]
                        status = animCurve

                    else:
                        attrDict[ 'input' ] = attrInput[ static ]
                        status = static

                else:
                    attrDict[ 'input' ] = attrInput[ static ]
                    status = static

                if status == static:

                    value = 0

                    if attrDict[ 'dataType' ] == 'enum':
                        value = mc.getAttr( node + '.' + attr, asString = True )
                    else:
                        value = mc.getAttr( node + '.' + attr )

                    if attrDict[ 'dataType' ] in floatDataTypes:
                        value = round( value, floatPrec )

                    if attrDict[ 'dataType' ] in angleDataTypes:
                        # gibt beim laden der pose nach dem guide mode falsche Rotationswerte,
                        # die ueberhaupt umgerechnet, sie wurden doch mit getAttr abgefragt
                        # value = round( math.degrees(value), floatPrec )
                        value = round( value, floatPrec )

                    attrDict[ 'value' ] = value

                if len( attrDict ) == 0:
                    attrDict = None

                dict[ attr ] = attrDict

        return dict

    def get_char_handles( self, characterSet, dict = None ):
        if dict is None:
            dict = { }
        handles = [ ]

        attr = self.aniMetaDataAttrName

        if len( dict ) > 0:
            handles = self.get_nodes( characterSet, dict, attr, True )

        return sorted( handles )

    def get_handles( self, character = None, mode = 'select', side = kLeft ):

        if not character:
            character = self.get_active_char()

        handles = [ ]

        if side == kAll:

            handles = self.get_char_handles( character, { 'Type': kHandle, 'Side': kAll } )

            # Add the Main Control to the list
            handles += self.get_char_handles( character,{ 'Type': kMain} )

        elif side == kSelection:
            handles = mc.ls( sl = True )
        else:
            handles = self.get_char_handles( character, { 'Type': kHandle, 'Side': side } )

        if len( handles ) > 0:
            if mode == 'select':
                mc.select( handles, r = True )

            elif mode == 'key':
                mc.setKeyframe( handles, i=True )
                mc.setKeyframe( handles )

            elif mode == 'reset':
                mc.undoInfo( openChunk = True )
                try:
                    for handle in handles:
                        self.reset_handle( self.find_node( character, handle ) )
                finally:
                    mc.undoInfo( closeChunk = True )
        else:
            mc.warning( 'No handles to ' + mode + '. Please check you character set selection.' )

        return True

    def get_joint_transform(self, *args):

        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']

        charRoot = args[0]

        # Remove Symmetry Constraints
        joint_grp = self.find_node(charRoot, 'Joint_Grp')

        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']

        #####################################################################################
        #
        # Store joint positions
        # ... or the positions may be off when the constraints get deleted
        jointDict = {}

        joints = mc.listRelatives(joint_grp, c=True, ad=True, pa=True, type='joint')

        for joint in joints:

            joint_short = self.short_name( joint )

            jointDict[joint_short] = {}
            for attr in attrs:
                jointDict[joint_short][attr] = mc.getAttr(joint + '.' + attr)

        return jointDict
        # Store joint positions
        #
        #####################################################################################

    def import_drivenKeys( self, fileName ):

        with open( fileName ) as file_obj:
            data_json = file_obj.read()

        drivenKeys = json.loads( data_json )

        anim = Anim()

        for curve in drivenKeys.keys():

            if mc.objExists( curve ):
                mc.delete( curve )

            curve = mc.createNode( drivenKeys[curve]['type'], name=self.short_name(curve) , ss=True )

            mc.connectAttr( drivenKeys[curve]['input'], curve + '.input', f=True )

            mc.connectAttr(  curve + '.output' , drivenKeys[curve][ 'output' ], f = True )


            anim.set_anim_curve_data( curve, drivenKeys[curve] )

    def import_drivenKeys_ui( self, *args, **kwargs ):

        workDir = mc.workspace( q = True, directory = True )
        result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Load',
                                 cap = 'Load Skeleton', fm = 1 )
        fileName = result[ 0 ]
        print( 'Driven key file to import:', fileName )
        self.import_drivenKeys( fileName )

    def import_joints( self, fileName, create=True, parent=True, root=None ):

        with open(fileName ) as f:
            data_json = f.read()

        joints = json.loads( data_json )

        self.joints_build( joints, create, parent, root )


    def import_joints_ui( self, *args, **kwargs ):

        workDir = mc.workspace( q = True, directory = True )
        result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Load',
                                 cap = 'Load Skeleton', fm = 1 )
        fileName = result[ 0 ]
        print( 'Skeleton file to import:', fileName )
        rootNode = self.import_joints( fileName )
        return rootNode


    def joints_build(self, data, create=True, parent=True, root=None ):

        joints = sorted( data['Skeleton']['Joints'].keys() )


        if create:
            # Create if necessary
            for i in range( len( joints )):
                xform_data = data['Skeleton']['Joints'][joints[i]]
                if not mc.objExists( joints[i] ):
                    mc.createNode( xform_data['nodeType'], name=self.short_name(joints[i] ) )

                else:
                    mc.warning('aniMeta.import_joints: There is already a node called: ' + joints[i] )
        out = []

        if parent:
            # Create if necessary
            for i in range( len( joints )):
                xform_data = data['Skeleton']['Joints'][ joints[i] ]

                if 'parent' in xform_data:
                    parent = mc.listRelatives( joints[i], p=True, pa=True ) or []
                    if len( parent ):
                        if parent[0] != xform_data['parent']:
                            try:
                                if mc.objExists( xform_data['parent'] ):
                                    mc.parent( joints[i], xform_data['parent'] )
                            except:
                                pass
                    else:
                        if mc.objExists( xform_data['parent'] ):
                            mc.parent( joints[i], xform_data['parent'])



        for i in range(len(joints)):

            xform_data = data['Skeleton']['Joints'][joints[i]]

            #root = 'guide'
            #name = 'body_C0_root'
            # If there are multiple nodes by this name, find the one under the given root
            jnt = None
            jnts = mc.ls( joints[i], l=True) or []
            if len(jnts) == 1:
                jnt = jnts[0]
            elif len(jnts) > 1:
                if root is None:
                    mc.warning( 'Please specify a root node, because multiple objects exist with the name:', joints[i] )
                for i in range(len(jnts)):
                    buff = jnts[i].split('|')
                    if buff[1] == root:
                        jnt = jnts[i]
                        break
            if jnt:

                for attr in self.attrs:
                    if attr in xform_data:
                        try:
                            mc.setAttr( jnt + '.' + attr, l=False )
                            mc.setAttr( jnt + '.' + attr, float( xform_data[attr] ) )
                        except:
                            #print( 'Issue loading:',  jnt + '.' + attr )
                            pass
                    else:
                        if attr in ['sx', 'sy', 'sz', 'radius']:
                            try:
                                mc.setAttr( jnt + '.' + attr, l=False )
                                mc.setAttr( jnt + '.' + attr, 1.0 )
                            except:
                                #print( 'Issue loading:',  jnt + '.' + attr )
                                pass
                        else:
                            try:
                                mc.setAttr( jnt + '.' + attr, 0.0 )
                            except:
                                #print( 'Issue loading:',  jnt + '.' + attr )
                                pass
                if 'offsetParentMatrix' in xform_data:
                    mc.setAttr( jnt + '.offsetParentMatrix',  xform_data['offsetParentMatrix'], type='matrix' )

    def lock_trs( self, node, lock=True):
        for attr in ['t', 'r', 's']:
            for axis in ['x', 'y', 'z']:
                mc.setAttr(node + '.' + attr + axis, l=lock, k=lock, cb=lock)

    def lock_attrs( self, node, attrList):

        node = self.get_path( node )

        if node is not None:
            if mc.objExists( node.fullPathName() ):
                for attr in attrList:
                    mc.setAttr(node.fullPathName() + '.' + attr, l=1, k=0, cb=0)

    def mirror_handle( self ):
        sel = mc.ls( sl = True )

        mode = mc.optionVar( query = 'aniMetaMirrorTrans_Mode' )
        mirror_t = mc.optionVar( query = 'aniMetaMirrorTrans_AttrT' )
        mirror_r = mc.optionVar( query = 'aniMetaMirrorTrans_AttrR' )
        axis = mc.optionVar( query = 'aniMetaMirrorTrans_Axis' )
        mirror_s = False

        space = kLocal
        refObject = None
        setKeyframe = False

        if len( sel ) == 2:
            m = self.get_matrix( sel[ 0 ], space )
            m = self.mirror_matrix( m, mode, space, refObject, axis )
            self.set_matrix( sel[ 1 ], m, space, setKeyframe, mirror_t, mirror_r, mirror_s )
        else:
            mc.warning( "aniMeta Mirror: Please select two transforms or joints to mirror." )

    def parent_joints( self, node, parent, char ):

        # print 'parent_skeleton', node, parent, char

        nodePathShort = ''
        nodePathLong = ''
        parentPathShort = ''
        parentPathLong = ''

        if parent is not None and node is not None:

            if isinstance( node, str ):
                nodePathShort = node
                nodePathLong = self.find_node( char, node )
            else:
                nodePathShort = node.partialPathName()
                nodePathLong = node.fullPathName()

            if isinstance( parent, str ):
                parentPathShort = parent
                parentPathLong = self.find_node( char, parent )
            else:
                parentPathShort = parent.partialPathName()
                parentPathLong = parent.fullPathName()

            currentParent = mc.listRelatives( nodePathLong, p = True, pa = False )

            doParent = True

            # Check to see if the current parent is already the one we want, if so, skip parenting
            if currentParent is not None:
                if currentParent[ 0 ] == parentPathShort:
                    doParent = False

            if doParent:
                try:
                    mc.parent( nodePathLong, parentPathLong, r = True )
                except:
                    pass

    def parent_skeleton( self, node, parent, char ):

        # print 'parent_skeleton', node, parent, char

        nodePathShort = ''
        nodePathLong = ''
        parentPathShort = ''
        parentPathLong = ''

        if parent is not None and node is not None:
            if isinstance( node, str ):
                nodePathShort = node
                nodePathLong = self.find_node( char, node )
            else:
                nodePathShort = node.partialPathName()
                nodePathLong = node.fullPathName()

            if isinstance( parent, str ):
                parentPathShort = parent
                parentPathLong = self.find_node( char, parent )
            else:
                parentPathShort = parent.partialPathName()
                parentPathLong = parent.fullPathName()

            currentParent = mc.listRelatives( nodePathLong, p = True, pa = False )

            doParent = True

            # Check to see if the current parent is already the one we want, if so, skip parenting
            if currentParent is not None:
                if currentParent[ 0 ] == parentPathShort:
                    doParent = False

            if doParent:
                try:
                    mc.parent( nodePathLong, parentPathLong, r = True )
                except:
                    pass

    def set_pose( self, pose, handles=kAll, space=kLocal ):

        char = self.get_active_char()

        if 'data' in pose[ 'aniMeta' ][ 1 ]:

            nodes = sorted( pose[ 'aniMeta' ][ 1 ][ 'data' ].keys() )

            mc.undoInfo( openChunk=True )

            for i in range(2):

                for node in nodes:

                    handle = self.find_node( char, node )

                    if handle is not None:

                        attrs = pose[ 'aniMeta' ][ 1 ][ 'data' ][ node ]

                        for attribute in attrs:

                            if attribute != 'world_matrix':
                                if space == kLocal:
                                    value = pose[ 'aniMeta' ][ 1 ][ 'data' ][ node ][ attribute ]
                                    try:
                                        mc.setAttr( handle + '.' + attribute, value )
                                    except:
                                        pass
                                else:
                                    pass

            mc.undoInfo( closeChunk=True )

    def reset_handle(self, node):

        attrs = mc.listAttr(node, k=True)
        if attrs:
            for attr in attrs:
                default = mc.attributeQuery(attr, node=node, listDefault=True)[0]
                try:
                    mc.setAttr(node + '.' + attr, default)
                except:
                    pass

    def set_joint_transform(self, *args):

        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']

        charRoot = args[0]
        jointDict = args[1]
        joint_grp = self.find_node(charRoot, 'Joint_Grp')
        joints = mc.listRelatives(joint_grp, c=True, ad=True, type='joint', pa=True)

        for joint in joints:

            joint_short = self.short_name(  joint )
            joint_path  = self.find_node(  charRoot, joint )

            if joint_short not in jointDict:
                mc.warning( 'aniMeta set joint transform: can not find {} in joint dict.'.format( joint_short ))
            else:
                for attr in attrs:
                    if attr in jointDict[joint_short]:
                        try:
                            mc.setAttr( joint_path + '.' + attr, jointDict[joint_short][attr])
                        except:
                            pass

    def swap_pose( self, *args, **kwargs ):

        mc.undoInfo( openChunk=True )

        mode = 'all'
        symMode = 'mirror'
        symDir = 'leftToRight'

        if 'mode' in kwargs:
            mode = kwargs['mode']
        if 'symMode' in kwargs:
            symMode = kwargs['symMode']
        if 'symDir' in kwargs:
            symDir = kwargs['symDir']

        char = self.get_active_char()

        if char is None:
            mc.warning( 'Please select a character set.' )
            return False

        char_Lft = char
        char_Rgt = char

        if 'Lft' in char:
            char_Rgt = char.replace( 'Lft', 'Rgt' )

            if not mc.objExists( char_Rgt ):
                mc.warning( 'Can not get right side of character set, aborting ...' )
                return False

        if 'Rgt' in char:
            char_Lft = char.replace( 'Rgt', 'Lft' )
            if not mc.objExists( char_Lft ):
                mc.warning( 'Can not get left side of character set, aborting ...' )
                return False

        handles_Lft = [ ]
        handles_Rgt = [ ]
        handles_Ctr = [ ]
        iks         = [ ]

        if mode == 'all':
            arm_ik_Lft_name = 'Arm_IK_Lft'
            arm_ik_Rgt_name = 'Arm_IK_Rgt'
            leg_ik_Lft_name = 'Leg_IK_Lft'
            leg_ik_Rgt_name = 'Leg_IK_Rgt'

            # IK Attributes

            iks = [ arm_ik_Lft_name, arm_ik_Rgt_name, leg_ik_Lft_name, leg_ik_Rgt_name ]
            ik_dict = {}

            for ik in iks:

                loc = self.find_node( char, ik )

                data = {}

                for attr in mc.listAttr( loc, ud=True, k=True ):
                    data[attr] = mc.getAttr( loc + '.' + attr )

                ik_dict[ik] = data


            handles_Lft = self.get_char_handles( char_Lft, { 'Side': kLeft } )
            handles_Rgt = self.get_char_handles( char_Rgt, { 'Side': kRight } )
            handles_Ctr = self.get_char_handles( char, { 'Side': kCenter } )

        elif mode == 'sel':

            sel = mc.ls( sl = True, l = False )

            for s in sel:
                short = self.short_name( s )
                if self.match_metaData( s, { 'Type': kHandle, 'Side': kLeft } ):
                    if short not in handles_Lft:
                        handles_Lft.append( short )
                        handles_Rgt.append( short.replace( 'Lft', 'Rgt' ) )
                elif self.match_metaData( s, { 'Type': kHandle, 'Side': kRight } ):
                    if short not in handles_Rgt:
                        handles_Rgt.append( short )
                        handles_Lft.append( short.replace( 'Rgt', 'Lft' ) )
                elif self.match_metaData( s, { 'Type': kHandle, 'Side': kCenter } ):
                    if short not in handles_Ctr:
                        handles_Ctr.append( short )
        mats = { }

        for handle in handles_Lft:
            mat = self.get_matrix( handle, kLocal )
            if mat is not None:
                mats[ handle ] = mat

        for handle in handles_Rgt:
            mat = self.get_matrix( handle, kLocal )
            if mat is not None:
                mats[ handle ] = mat

        for handle in handles_Ctr:
            mat = self.get_matrix( handle, kLocal )
            if mat is not None:
                mats[ handle ] = mat

        # We need this so we can undo this operation in one go
        mc.undoInfo( openChunk = True )
        # try:
        if symMode == 'swap':

            mirror_mats = {}

            for handle in handles_Ctr:
                mirror = self.mirror_matrix( mats[ handle ], mode = kBasic, space = kLocal )

                # cmd  += 'mc.spaceLocator()\n'
                self.set_matrix( handle, mirror, kLocal )

            for handle in handles_Rgt:
                dataDict = self.get_metaData( handle )
                if 'Rgt' in handle:
                    nameLft = handle.replace( 'Rgt', 'Lft' )

                    if nameLft in mats:
                        if 'Mirror' in dataDict:
                            mirror = self.mirror_matrix( mats[ nameLft ], mode = dataDict[ 'Mirror' ], space = kLocal )
                            self.set_matrix( handle, mirror, kLocal )

            for handle in handles_Lft:
                dataDict = self.get_metaData( handle )
                if 'Lft' in handle:
                    nameRgt = handle.replace( 'Lft', 'Rgt' )
                    if nameRgt in mats:
                        if 'Mirror' in dataDict:
                            mirror = self.mirror_matrix( mats[ nameRgt ], mode = dataDict[ 'Mirror' ], space = kLocal )
                            self.set_matrix( handle, mirror, kLocal )

            # IK
            if len(iks):
                for ik in iks:

                    if 'Lft' in ik:
                        opposite = ik.replace('Lft', 'Rgt')

                    elif 'Rgt' in ik:
                        opposite = ik.replace('Rgt', 'Lft')

                    node = self.find_node(char, ik)

                    for attr in ik_dict[ik].keys():
                        mc.setAttr(node + '.' + attr, ik_dict[opposite][attr])
            if mode == 'all':
                self.flip_tangents( )
            if mode == 'sel':
                self.flip_tangents( handles_Ctr+ handles_Rgt+ handles_Lft )

        elif symMode == 'mirror':

            if symDir == 'leftToRight':
                for handle in handles_Rgt:
                    dataDict = self.get_metaData( handle )
                    # Only Mirror nodes that are joints or transforms, not IK Locs
                    if 'Mirror' in dataDict:
                        if 'Rgt' in handle:
                            nameLft = handle.replace( 'Rgt', 'Lft' )
                            mirror = self.mirror_matrix( mats[ nameLft ], mode = dataDict[ 'Mirror' ], space = kLocal )
                            self.set_matrix( handle, mirror, kLocal )

            elif symDir == 'rightToLeft':
                for handle in handles_Lft:
                    dataDict = self.get_metaData( handle )
                    if 'Lft' in handle:
                        nameRgt = handle.replace( 'Lft', 'Rgt' )
                        if nameRgt in mats:
                            mirror = self.mirror_matrix( mats[ nameRgt ], mode = dataDict[ 'Mirror' ], space = kLocal )
                            self.set_matrix( handle, mirror, kLocal )
                        else:
                            mc.warning( nameRgt + ' can not be found in mats_Rgt dict.' )

            mc.undoInfo( closeChunk = True )


        mc.undoInfo( closeChunk=True )

    def flip_tangents(self, nodes=[]):

        current = mc.currentTime(query=True)

        char = self.get_active_char()
        if len(nodes) == 0:

            nodes = self.get_char_handles(char, {'Type':  kHandle, 'Side': kAll})

        mirror = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ', 'scaleX', 'scaleY',
                  'scaleZ']
        if len( nodes ) > 0:
            angles={}

            cmd = ''

            for node in nodes:

                attrs = mc.listAttr(node, k=True)
                for attr in attrs:
                    if attr in mirror:
                        # Query Angles and lock
                        try:
                            if 'Lft' in node:
                                node_mirror = node.replace('Lft', 'Rgt')
                            elif 'Rgt' in node:
                                node_mirror = node.replace('Rgt', 'Lft')
                            else:
                                node_mirror = node

                            node        = self.find_node( char, node )
                            node_mirror = self.find_node( char, node_mirror )

                            meta = self.get_metaData( node )

                            inv=False

                            if 'Mirror' in meta:
                                type = meta['Mirror']

                                if type == kBasic:
                                    if attr in [ 'translateX', 'rotateZ', 'rotateY']:
                                        inv=True

                            in_angle  = mc.keyTangent(node_mirror, attribute=attr, query=True, inAngle=True,  time=(current, current))[0]
                            out_angle = mc.keyTangent(node_mirror, attribute=attr, query=True, outAngle=True, time=(current, current))[0]
                            lock      = mc.keyTangent(node_mirror, attribute=attr, query=True, lock=True,     time=(current, current))[0]

                            if inv:
                                in_angle *= -1
                                out_angle *= -1

                            cmd += 'keyTangent -edit -attribute '+attr+' -time "'+str(current)+':'+str(current)+'" -lock 0 '+node+';\n'
                            cmd += 'keyTangent -edit -attribute '+attr+' -time "'+str(current)+':'+str(current)+'" -ia '+str(in_angle)+' -oa '+str(out_angle)+' '+node+';\n'
                            cmd += 'keyTangent -edit -attribute '+attr+' -time "'+str(current)+':'+str(current)+'" -lock '+str(int(lock))+' '+node+';\n'

                        except:
                            pass

            if len(cmd):
                mm.eval( cmd )

    def swap_rotation_with_parent(self, node):

        node = self.get_path( node )

        parent = mc.listRelatives( node.fullPathName(), p=True, pa=True)[0]

        r = mc.getAttr( parent + '.r')[0]

        for attr in ['rx','ry','rz']:
            mc.setAttr( parent + '.' + attr, l=0)
            mc.setAttr( node.fullPathName() + '.' + attr, l=0)

        mc.setAttr(parent + '.r', 0, 0, 0)

        mc.setAttr( node.fullPathName() + '.r', r[0], r[1], r[2] )

    def skeleton_export_dialog( self, *args, **kwargs ):
        jnts = mc.ls( sl = True ) or [ ]

        if len( jnts ) > 0:
            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Save',
                                     cap = 'Save Skeleton' )

            fileName = result[ 0 ]

            self.skeleton_export( jnts, fileName )

            print( 'Skeleton exported to file ', fileName )

    def skeleton_import_dialog( self, *args, **kwargs ):

        workDir = mc.workspace( q = True, directory = True )
        result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Load',
                                 cap = 'Load Skeleton', fm = 1 )
        fileName = result[ 0 ]
        print( 'Skeleton file to import:', fileName )
        rootNode = self.skeleton_import( fileName )

    def switch_world_orient(self, *args, **kwargs):

        attrName = 'worldOrient'

        node = args[0]

        # If the user wants a specific state, we will use the one we get
        useState = False
        customState = False

        if len(args) > 1:
            useState = True
            customState = args[1]

        char = self.get_active_char()

        ctrl = self.find_node( char, node )

        if ctrl is not None:
            if mc.objExists( ctrl ):
                state = mc.getAttr( node + '.' + attrName )

                wm = self.get_matrix( node, space=kWorld )

                if useState:
                    state = customState
                else:
                    state = 1-state
                mc.setAttr( node +'.' + attrName, state )

                self.set_matrix( node, wm, setTranslate=False, setScale=False )
        else:
            mc.warning('aniMeta: Can not find{}.'.format(node))

    def switch_space(self, *args, **kwargs):

        attrName = 'space'

        node  = args[0]
        space = args[1]

        char = self.get_active_char()

        ctrl = self.find_node( char, node )

        if ctrl is not None:
            if mc.objExists( ctrl ):


                wm = self.get_matrix( ctrl, space=kWorld )

                mc.setAttr( node +'.' + attrName, space )

                self.set_matrix( ctrl, wm )
        else:
            mc.warning('aniMeta: Can not find{}.'.format(node))

# Skeleton I/O
#
######################################################################################################################

# Rig
#
######################################################################################

######################################################################################
#
# Char

class Char( Rig ):

    def __init__(self):
        super( Char, self ).__init__()

    def build_guides(self, *args):

        charRoot  = args[0]
        guideList = args[1]
        ctrlDict  = args[2]
        guideDict = args[3]
        data      = args[4]

        # Setting this to True causes issues with the A-Pose
        swap_rot = False

        if len(args)>5:
            swap_rot = args[5]

        rot_offset = om.MEulerRotation( 0,0,0 )
        metaData = self.get_metaData( charRoot )

        ctrlDict['offsetMatrix'] = rot_offset.asMatrix()

        if guideList:
            for guide in guideList:
                # This returns a string if the node exists
                guide_ctrl = self.find_node( charRoot, guide[ 0 ] )
                guide_tgt = self.find_node( charRoot, guide[ 1 ] )

                ctrlDict[ 'name' ] = guide[ 0 ]
                ctrlDict[ 'matchTransform' ] = guide_tgt
                ctrlDict[ 'constraint' ] = self.kParent

                if len( guide ) > 4:
                    ctrlDict[ 'offsetMatrix' ] = guide[ 4 ]
                else:
                    ctrlDict['offsetMatrix'] = rot_offset.asMatrix()

                if guide[ 2 ] in guideDict:
                    ctrlDict[ 'parent' ] = guideDict[ guide[ 2 ] ]
                else:
                    ctrlDict[ 'parent' ] = guide[ 2 ]

                # Create the Guide Control if it doesn`t exist, yet
                if guide_ctrl is not None:
                    if mc.objExists( guide[1] ):
                        mc.parentConstraint( guide_ctrl, guide_tgt, mo=True )
                    # From now on we want an MDagPath
                    guide_ctrl = self.get_path( guide_ctrl )
                else:
                    guide_ctrl = self.create_handle( **ctrlDict )

                    # Check whether we need to build the right side for a left-sided guide
                    if 'Lft' in ctrlDict['name']:

                        # Right side version of the guide´s name
                        rgt_name = ctrlDict['name'].replace( 'Lft', 'Rgt' )

                        # Get the parents DAG path
                        parent_rgt = ctrlDict[ 'parent' ]

                        if 'Lft' in ctrlDict[ 'parent' ].partialPathName():
                            #parent_rgt = ctrlDict[ 'parent' ].fullPathName().replace( 'Lft', 'Rgt')
                            parent_rgt = self.short_name( ctrlDict[ 'parent' ].fullPathName() ).replace( 'Lft', 'Rgt')
                            parent_rgt = self.find_node( charRoot, parent_rgt )
                            parent_rgt = self.get_path( parent_rgt )

                        #######################################################################################
                        # Create right side guide groups and symConstraints
                        # To make symConstraints work, we need to create them for the guides and their parents
                        # in this section we create additional transforms above the right side guides

                        # Get the parent
                        parent_grp_lft = mc.listRelatives( guide_ctrl.fullPathName(), p=True, pa=True  )[0]

                        #if self.short_name(parent_rgt) != 'Guides_Body_Grp':

                        # Get the short name
                        parent_grp_lft_short = self.short_name( parent_grp_lft )

                        # Get the right side version of this name
                        parent_joint_lft_short = parent_grp_lft_short.replace( 'Lft', '_joint_Lft' )
                        parent_grp_rgt_short = parent_grp_lft_short.replace( 'Lft', 'Rgt' )

                        # We create a joint to joint symConstraint as there seem to be errors when not using joints
                        # with symConstraint nodes
                        parent_joint_grp_lft = mc.createNode('joint', name=parent_joint_lft_short, parent=parent_grp_lft )
                        mc.setAttr( parent_joint_grp_lft+'.v', False )

                        # Get the parent`s parent of this group so we can parent the new group
                        grandparent_grp_lft = mc.listRelatives( parent_grp_lft, p=True, pa=True )[0]

                        # Get the short name of the grandparent
                        grandparent_grp_lft_short = self.short_name( grandparent_grp_lft )

                        # Get the right side version of this name
                        grandparent_grp_rgt_short = grandparent_grp_lft_short.replace( 'Lft', 'Rgt' )

                        # Get the long DAG path
                        grandparent_grp_rgt = self.find_node( charRoot, grandparent_grp_rgt_short )

                        parent_rgt_node = mc.createNode( 'joint', name=parent_grp_rgt_short, parent=grandparent_grp_rgt, ss=True )
                        mc.setAttr( parent_rgt_node+'.v', False )

                        # Add an offset matrix to first nodes off the centre to make the symConstraints work with standard transforms, the offset is 180 on rx
                        if not 'Lft' in grandparent_grp_lft_short:
                            offset_matrix = [1.0, 0.0, 0.0, 0.0, 0.0, -1, 0.0, 0.0, 0.0, 0.0, -1, 0.0, 0.0, 0.0, 0.0, 1.0]

                            mc.setAttr(  parent_rgt_node+ '.offsetParentMatrix', offset_matrix, typ='matrix')

                        self.create_sym_constraint( parent_joint_grp_lft , parent_rgt_node )

                        # Create right side guide groups and symConstraints
                        #######################################################################################

                        guide_rgt = mc.createNode( 'joint', name=rgt_name, parent=parent_rgt_node, ss=True )
                        mc.setAttr( guide_rgt+'.v', False )

                        self.create_sym_constraint( guide_ctrl, guide_rgt )

                guideDict[ ctrlDict[ 'name' ] ] = guide_ctrl

                if guide_ctrl is not None:
                    if mc.objExists( guide_ctrl.fullPathName() ):
                        if swap_rot:
                            self.swap_rotation_with_parent( guide_ctrl )
                        self.lock_attrs( guide_ctrl, guide[ 3 ] )
                        self.set_metaData( guide_ctrl , data )
                    else:
                        mc.warning( 'aniMeta: There was a problem creating guide', guide[ 0 ] )
        return guideDict

    def build_body_guides( self, *args ):
        sel = None
        type = kBiped
        skipExisting = False
        if args:
            sel = args[0]

            if len( args ) == 2:
                type = args[1]

            if len( args ) == 3:
                skipExisting = args[2]
        else:
            sel = self.get_active_char()

        charRoot = None
        metaData = { }

        # Hack Alert!
        if type == kBipedRoot:
            type = kBiped

        if sel:
            metaData = self.get_metaData( sel )
            if 'RigType' in metaData:
                if metaData[ 'RigType' ] == kBiped or metaData[ 'RigType' ] == kBipedUE  or metaData[ 'RigType' ] == kQuadruped :
                    charRoot = sel
                type = metaData[ 'RigType' ]

        if not charRoot:
            mc.warning( 'Please select a Biped Root Group.' )
        else:
            metaData = self.get_metaData( charRoot )
            rigState = None

            if 'RigState' in metaData:
                rigState = metaData[ 'RigState' ]
            else:
                rigState = kRigStateBind

            if rigState == kRigStateControl:
                # self.rig_control_biped_delete()
                rigState = kRigStateBind
            #if rigState == kRigStateGuide:
            #    mc.warning( 'aniMeta: The rig already is already in guide mode.' )
            #    return
            #if rigState != kRigStateBind:
            #    mc.warning( 'aniMeta: Wrong state to create Guides.' )
            #else:
            metaData[ 'RigState' ] = kRigStateGuide

            # Set Default Rig Display options to be used when the rig is switched to control mode
            if 'RigDisplay' not in metaData:
                metaData[ 'RigDisplay' ] = { 'display_Joint': 1, 'show_Rig': 1, 'show_Joints': 0, 'show_Guides': 0, 'display_Geo': 2 }

            self.set_metaData( charRoot, metaData )

            joints = [ ]

            if type == kBiped :
                joints = [ 'Eye_Lft_Jnt',
                           'LegUp_Lft_Jnt',
                           'LegLo_Lft_Jnt',
                           'Foot_Lft_Jnt',
                           'Heel_Lft_Jnt',
                           'Toes_Lft_Jnt',
                           'ToesTip_Lft_Jnt',
                           'Clavicle_Lft_Jnt',
                           'ArmUp_Lft_Jnt',
                           'Shoulder_Lft_upVec',
                           'Hips_Lft_upVec',
                           'ArmLo_Lft_Jnt',
                           'Hand_Lft_Jnt',
                           'Palm_Lft_Jnt',
                           'Prop_Lft_Jnt',
                           'Thumb1_Lft_Jnt', 'Thumb2_Lft_Jnt', 'Thumb3_Lft_Jnt',
                           'Index1_Lft_Jnt', 'Index2_Lft_Jnt', 'Index3_Lft_Jnt', 'Index4_Lft_Jnt',
                           'Middle1_Lft_Jnt', 'Middle2_Lft_Jnt', 'Middle3_Lft_Jnt', 'Middle4_Lft_Jnt',
                           'Ring1_Lft_Jnt', 'Ring2_Lft_Jnt', 'Ring3_Lft_Jnt', 'Ring4_Lft_Jnt',
                           'Pinky1_Lft_Jnt', 'Pinky2_Lft_Jnt', 'Pinky3_Lft_Jnt', 'Pinky4_Lft_Jnt'
                           ]
            if type == kBipedUE:
                joints = [
                           'thigh_l',
                           'calf_l',
                           'foot_l',
                           'ball_l',
                           'clavicle_l',
                           'upperarm_l',
                           'lowerarm_l',
                           'hand_l',
                           'Shoulder_Lft_upVec',
                           'Hips_Lft_upVec',
                           'Heel_Lft',
                           'thumb_01_l', 'thumb_02_l', 'thumb_03_l',
                           #'index_metacarpal_l', 'middle_metacarpal_l', 'ring_metacarpal_l', 'pinky_metacarpal_l',
                           'index_01_l', 'index_02_l', 'index_03_l',
                           'middle_01_l', 'middle_02_l', 'middle_03_l',
                           'ring_01_l', 'ring_02_l', 'ring_03_l',
                           'pinky_01_l', 'pinky_02_l', 'pinky_03_l'
                           ]
            elif type == kQuadrupedRoot:
                joints = [ 'Eye_Lft_Jnt',
                           'Scapula_Lft_Jnt', 'Humerus_Lft_Jnt', 'Radius_Lft_Jnt', 'CannonFront_Lft_Jnt',
                           'PasternFront_Lft_Jnt', 'HoofFront_Lft_Jnt', 'HoofFrontTip_Lft_Jnt',
                           'Femur_Lft_Jnt', 'Fibula_Lft_Jnt', 'CannonBack_Lft_Jnt', 'PasternBack_Lft_Jnt',
                           'HoofBack_Lft_Jnt', 'HoofBackTip_Lft_Jnt',
                           'Ear_Lft_Jnt', 'EarTip_Lft_Jnt'
                           ]

            data = { }
            data[ 'Type' ] = kBodyGuide

            for joint_lft in joints:
                joint_rgt = None

                if 'Lft' in joint_lft:
                    joint_rgt = joint_lft.replace( 'Lft', 'Rgt' )
                if '_l' in joint_lft:
                    joint_rgt = joint_lft.replace( '_l', '_r' )

                if joint_rgt is not None:

                    jl = self.find_node( charRoot, joint_lft )
                    jr = self.find_node( charRoot, joint_rgt )

                    if jl is not None and jr is not None:

                        con = self.create_sym_constraint( jl, jr )
                        self.set_metaData( con, data )

                else:
                    mc.warning( 'aniMeta: No right joint found for node ' + joint_lft )

            guidesGrp = self.find_node( charRoot, 'Guides_Grp' )
            guideGrp = self.find_node( charRoot, 'Guides_Body_Grp' )

            if guideGrp is None:
                guideGrp = mc.createNode( 'transform', name = 'Guides_Body_Grp', ss = True, parent = guidesGrp )

            self.set_metaData( guideGrp, data )

            attrList = [ 'sx', 'sy', 'sz', 'v' ]

            guideDict = { }

            ctrlDict = { }
            ctrlDict[ 'color' ] = (1, 0.7, 0)
            ctrlDict[ 'radius' ] = 2
            ctrlDict[ 'constraint' ] = self.kParent
            ctrlDict[ 'shapeType' ] = self.kSphere
            ctrlDict[ 'character' ] = charRoot
            ctrlDict[ 'globalScale' ] = True

            guideList = [ ]

            guide_sfx = '_Guide'

            if type == kBipedUE:

                # If Guides have been created for this rig, skip this section
                if skipExisting:
                    node = self.find_node(charRoot, 'Hips'+guide_sfx)
                    if node is not None:
                        return


                attrList = [ 'sx', 'sy', 'sz', 'v' ]

                #rot_offset_1 = om.MEulerRotation( 0, math.radians(  90 ),math.radians(  -90 ) ).asMatrix()
                #rot_offset_2 = om.MEulerRotation( 0, math.radians(  90 ),math.radians(  0 ) ).asMatrix()
                #rot_offset_3 = om.MEulerRotation( math.radians(  90 ), math.radians(  0 ),math.radians( 0 ) ).asMatrix()
                #rot_offset_4 = om.MEulerRotation( math.radians(  180 ), math.radians( 0 ) ,math.radians( 0 ) ).asMatrix()

                rot_offset_1 = om.MEulerRotation(0, 0, 0).asMatrix()
                rot_offset_2 = om.MEulerRotation(0, 0, 0).asMatrix()
                rot_offset_3 = om.MEulerRotation(0, 0, 0).asMatrix()
                rot_offset_4 = om.MEulerRotation(0, 0, 0).asMatrix()

                #Should the Guide names be

                # Pelvis
                guideList.append( [ 'Hips'+guide_sfx, 'pelvis', guideGrp, attrList, rot_offset_1 ] )

                # spine_01
                guideList.append( [ 'Spine1'+guide_sfx, 'spine_01',  'Hips'+guide_sfx, attrList, rot_offset_1 ] )

                # spine_02
                guideList.append( [ 'Spine2'+guide_sfx, 'spine_02', 'Spine1'+guide_sfx, attrList, rot_offset_1 ] )

                # spine_03
                guideList.append( [ 'Spine3'+guide_sfx, 'spine_03', 'Spine2'+guide_sfx, attrList, rot_offset_1 ] )

                # spine_04
                guideList.append( [ 'Spine4'+guide_sfx, 'spine_04', 'Spine3'+guide_sfx, attrList, rot_offset_1 ] )

                # spine_05
                guideList.append( [ 'Spine5'+guide_sfx, 'spine_05', 'Spine4'+guide_sfx, attrList, rot_offset_1 ] )

                # neck_01
                guideList.append( [ 'Neck1'+guide_sfx, 'neck_01', 'Spine5'+guide_sfx, attrList, rot_offset_1 ] )

                # neck_02
                guideList.append( [ 'Neck2'+guide_sfx, 'neck_02', 'Neck1'+guide_sfx, attrList, rot_offset_1 ] )

                # head
                guideList.append( [ 'Head'+guide_sfx, 'head', 'Neck2'+guide_sfx, attrList, rot_offset_1 ] )

                # clavicle_l
                guideList.append( [ 'Clavicle_Lft'+guide_sfx, 'clavicle_l', 'Spine5'+guide_sfx, attrList, rot_offset_3  ] )

                # upperarm_l
                guideList.append( [ 'ArmUp_Lft'+guide_sfx, 'upperarm_l', 'Clavicle_Lft'+guide_sfx, attrList, rot_offset_3  ] )

                # lowerarm_l
                guideList.append( [ 'ArmLo_Lft'+guide_sfx, 'lowerarm_l', 'ArmUp_Lft'+guide_sfx, attrList, rot_offset_3  ] )

                # hand_l
                guideList.append( [ 'Hand_Lft'+guide_sfx, 'hand_l', 'ArmLo_Lft'+guide_sfx, attrList, rot_offset_4  ] )

                # thigh_l
                guideList.append( [ 'LegUp_Lft'+guide_sfx, 'thigh_l', 'Hips'+guide_sfx, attrList, rot_offset_1 ] )

                # calf_l
                guideList.append( [ 'LegLo_Lft'+guide_sfx, 'calf_l', 'LegUp_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # foot_l
                guideList.append( [ 'Foot_Lft'+guide_sfx, 'foot_l', 'LegLo_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # ball_l
                guideList.append( [ 'Ball_Lft'+guide_sfx, 'ball_l', 'Foot_Lft'+guide_sfx, attrList, rot_offset_2  ])

                # Shoulder Up Vec
                guideList.append( [ 'Shoulder_Lft_upVec'+guide_sfx, 'Shoulder_Lft_upVec', 'Clavicle_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # Hips Up Vec
                guideList.append( [ 'Hips_Lft_upVec'+guide_sfx, 'Hips_Lft_upVec', 'Hips'+guide_sfx, attrList, rot_offset_1 ] )

                # Heel Lft
                guideList.append( [ 'Heel_Lft'+guide_sfx, 'Heel_Lft',  'Foot_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # ToesTip Lft
                guideList.append( [ 'ToesTip_Lft'+guide_sfx, 'ToesTip_Lft',  'Ball_Lft'+guide_sfx, attrList   ] )

                # foot_l
                guideList.append( [ 'Foot_Lft'+guide_sfx, 'foot_l', 'LegLo_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # meta index
                guideList.append( [ 'IndexMeta_Lft'+guide_sfx, 'index_metacarpal_l', 'Hand_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # meta middle
                guideList.append( [ 'MiddleMeta_Lft'+guide_sfx, 'middle_metacarpal_l', 'Hand_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # ring middle
                guideList.append( [ 'RingMeta_Lft'+guide_sfx, 'ring_metacarpal_l', 'Hand_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # pinky middle
                guideList.append( [ 'PinkyMeta_Lft'+guide_sfx, 'pinky_metacarpal_l', 'Hand_Lft'+guide_sfx, attrList, rot_offset_1 ] )

                # Fingers
                fngr_1 = [ 'thumb', 'index', 'middle', 'ring', 'pinky'  ]
                fngr_2 = [ 'Thumb', 'Index', 'Middle', 'Ring', 'Pinky'  ]
                count = [ 4, 4, 4, 4, 4  ]

                for j in range( len ( fngr_1 )):
                    for i in range( 1, count[j] ):
                        name       = fngr_1[j] + '_0'+str( i ) + '_l'
                        guide_name = fngr_2[j] + str( i ) + '_Lft'+guide_sfx

                        if i == 1:
                            if fngr_2[j] == 'Thumb':
                                parent = 'Hand_Lft'+guide_sfx
                            else:
                                parent = fngr_2[j]+'Meta_Lft'+guide_sfx
                        else:
                            parent = fngr_2[j] + str( i-1 ) + '_Lft'+guide_sfx

                        guideList.append( [ guide_name, name, parent, attrList, rot_offset_4 ] )

                guideDict = self.build_guides( charRoot, guideList, ctrlDict, guideDict, data, False )

                # Position heel guide manually, we don't have a joint for this one
                heel_guide = self.find_node(charRoot, 'Heel_Lft_Guide')
                foot_guide = self.find_node(charRoot, 'Foot_Lft_Guide')
                mc.matchTransform( heel_guide, foot_guide)
                mc.setAttr( heel_guide + '.ty', 0)
                mc.xform(heel_guide, t=[0,3,0], relative=True, objectSpace=True )

                # Position toe_guide
                toestip_guide = self.find_node(charRoot, 'ToesTip_Lft_Guide')
                ball_guide = self.find_node(charRoot, 'Ball_Lft_Guide')
                mc.matchTransform( toestip_guide, ball_guide )
                mc.xform(toestip_guide, t=[10,0,0], relative=True, objectSpace=True )

                # Position shoulder_upVec
                upvec_guide = self.find_node(charRoot, 'Shoulder_Lft_upVec_Guide')
                shoulder_guide = self.find_node(charRoot, 'ArmUp_Lft_Guide')
                mc.matchTransform( upvec_guide, shoulder_guide, position=True, rotation=False)
                mc.xform(upvec_guide, t=[3,10,0], relative=True )

                # Position hips_guide
                hipsupvec_guide = self.find_node(charRoot, 'Hips_Lft_upVec_Guide')
                legup_guide = self.find_node(charRoot, 'LegUp_Lft_Guide')
                mc.matchTransform( hipsupvec_guide, legup_guide )
                mc.xform(hipsupvec_guide, t=[0,0,-10], relative=True, objectSpace=True )

            if type == kBiped:

                rot_offset_1 = om.MEulerRotation( 0, math.radians(  0 ),math.radians(  0 ) ).asMatrix()
                # Hips
                guideList.append( [ 'Hips_Guide', 'Hips_Jnt', guideGrp, attrList ] )

                # Spine1
                guideList.append( [ 'Spine1_Guide', 'Spine1_Jnt', 'Hips_Guide', attrList ] )

                # Spine2
                guideList.append( [ 'Spine2_Guide', 'Spine2_Jnt', 'Spine1_Guide', attrList ] )

                # Spine3
                guideList.append( [ 'Spine3_Guide', 'Spine3_Jnt', 'Spine2_Guide', attrList ] )

                # Chest
                guideList.append( [ 'Chest_Guide', 'Chest_Jnt', 'Spine3_Guide', attrList ] )

                # Neck
                guideList.append( [ 'Neck_Guide', 'Neck_Jnt', 'Chest_Guide', attrList ] )

                # Head
                guideList.append( [ 'Head_Guide', 'Head_Jnt', 'Neck_Guide', attrList ] )

                # Head Tip
                guideList.append( [ 'Head_Tip_Guide', 'Head_Jnt_Tip', 'Head_Guide', attrList ] )

                # Jaw
                guideList.append( [ 'Jaw_Guide', 'Jaw_Jnt', 'Head_Guide', attrList ] )

                # Jaw Tip
                guideList.append( [ 'Jaw_Tip_Guide', 'Jaw_Jnt_Tip', 'Jaw_Guide', attrList ] )

                # Eyes
                guideList.append( [ 'Eye_Lft_Guide', 'Eye_Lft_Jnt', 'Head_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Clavicle Lft
                guideList.append( [ 'Clavicle_Lft_Guide', 'Clavicle_Lft_Jnt', 'Chest_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # ArmUp Lft
                guideList.append( [ 'ArmUp_Lft_Guide', 'ArmUp_Lft_Jnt', 'Clavicle_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Shoulder Up Vec
                guideList.append( [ 'Shoulder_Lft_upVec_Guide', 'Shoulder_Lft_upVec', 'Clavicle_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # ArmLo Lft
                guideList.append( [ 'ArmLo_Lft_Guide', 'ArmLo_Lft_Jnt', 'ArmUp_Lft_Guide', ['sx', 'sy', 'sz', 'v' ] ] )

                # Hand Lft
                guideList.append(  [ 'Hand_Lft_Guide', 'Hand_Lft_Jnt', 'ArmLo_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Palm Lft
                guideList.append( [ 'Palm_Lft_Guide', 'Palm_Lft_Jnt', 'Hand_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Prop Lft
                guideList.append( [ 'Prop_Lft_Guide', 'Prop_Lft_Jnt', 'Palm_Lft_Guide',  [ 'sx', 'sy', 'sz', 'v' ]  ] )

                # LegUp Lft
                guideList.append( [ 'LegUp_Lft_Guide', 'LegUp_Lft_Jnt', 'Hips_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Hips Up Vec
                guideList.append( [ 'Hips_Lft_upVec_Guide', 'Hips_Lft_upVec', 'Hips_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # LegLo Lft
                guideList.append( [ 'LegLo_Lft_Guide', 'LegLo_Lft_Jnt', 'LegUp_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Foot Lft
                guideList.append(  [ 'Foot_Lft_Guide', 'Foot_Lft_Jnt', 'LegLo_Lft_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                attrList = [ 'sx', 'sy', 'sz', 'v' ]

                # Toes Lft
                guideList.append( [ 'Ball_Lft_Guide', 'Toes_Lft_Jnt', 'Foot_Lft_Guide', attrList ] )

                # Toes Tip Lft
                guideList.append( [ 'ToesTip_Lft_Guide', 'ToesTip_Lft_Jnt', 'Ball_Lft_Guide', attrList ] )

                # Heel Lft
                guideList.append( [ 'Heel_Lft_Guide', 'Heel_Lft_Jnt', 'Foot_Lft_Guide', attrList ] )

                print ('aniMeta: Create Guides')

                prop_guide = self.find_node( charRoot, 'Prop_Lft_Guide')
                if prop_guide is not None:
                    mc.setAttr( prop_guide+'.controlSize', 1)

                # Fingers
                fngr = [ 'Index', 'Pinky', 'Middle', 'Ring', 'Thumb'   ]

                for j in range( len ( fngr )):
                    for i in range( 1, 5 ):

                        if j == 4 and i == 4:
                            continue

                        name       = fngr[j] + str( i ) + '_Lft_Jnt'
                        guide_name = fngr[j] + str( i ) + '_Lft'+guide_sfx

                        if i == 1:
                            parent = 'Hand_Lft'+guide_sfx
                        else:
                            parent = fngr[j] + str( i-1 ) + '_Lft'+guide_sfx

                        guideList.append( [ guide_name, name, parent, [  'sx', 'sy', 'sz', 'v' ], rot_offset_1 ] )

                guideDict = self.build_guides( charRoot, guideList, ctrlDict, guideDict, data )

                m = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
                mc.setAttr( 'Clavicle_Rgt_Guide_Grp.offsetParentMatrix', m, typ='matrix' )

                '''
                # Fingers
                for fngr in [ 'Index', 'Pinky', 'Middle', 'Ring', 'Thumb'  ]:
                    for i in range( 1, 5 ):
                        ctrlDict[ 'name' ] = fngr + str( i ) + '_Lft_Guide'
                        ctrlDict[ 'matchTransform' ] = fngr + str( i ) + '_Lft_Jnt'
                        ctrlDict[ 'radius' ] = 1

                        if i == 1:
                            ctrlDict[ 'parent' ] = guideDict[ 'Palm_Lft_Guide' ]
                            attrList = [ 'sx', 'sy', 'sz', 'v' ]
                        else:
                            ctrlDict[ 'parent' ] = guideDict[ fngr + str( i - 1 ) + '_Lft_Guide' ]
                            attrList = [ 'ty', 'tz', 'rx', 'ry', 'sx', 'sy', 'sz', 'v' ]

                        if fngr is not 'Thumb':
                            guideDict[ ctrlDict[ 'name' ] ] = self.create_handle( **ctrlDict )
                            self.swap_rotation_with_parent( guideDict[ ctrlDict[ 'name' ] ] )
                            self.lock_attrs( guideDict[ ctrlDict[ 'name' ] ] , attrList )
                            self.set_metaData( guideDict[ ctrlDict[ 'name' ] ] , data )

                        if fngr is 'Thumb' and i < 4:
                            guideDict[ ctrlDict[ 'name' ] ] = self.create_handle( **ctrlDict )
                            self.swap_rotation_with_parent( guideDict[ ctrlDict[ 'name' ] ] )
                            self.lock_attrs( guideDict[ ctrlDict[ 'name' ] ], attrList )
                            self.set_metaData( guideDict[ ctrlDict[ 'name' ] ], data )
                '''
                for guide in guideDict.keys():
                    try:
                        mc.setAttr( guide + '.displayHandle', True )
                    except:
                        pass


            if type == kQuadrupedRoot:

                ctrlDict[ 'radius' ] = 0.3

                justTzRx = [ 'tx', 'ty', 'ry', 'rz', 'sx', 'sy', 'sz', 'v' ]

                # Hips
                guideList.append( [ 'Pelvis_Guide', 'Pelvis_Jnt', guideGrp, attrList ] )

                # Femur
                guideList.append( [ 'Femur_Guide', 'Femur_Lft_Jnt', 'Pelvis_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Fibula
                guideList.append( [ 'Fibula_Guide', 'Fibula_Lft_Jnt', 'Femur_Guide', justTzRx ] )

                # Cannon
                guideList.append( [ 'CannonBack_Guide', 'CannonBack_Lft_Jnt', 'Fibula_Guide',
                                    [ 'tx', 'ty', 'ry', 'rz', 'sx', 'sy', 'sz', 'v' ] ] )

                # Pastern
                guideList.append( [ 'PasternBack_Guide', 'PasternBack_Lft_Jnt', 'CannonBack_Guide',
                                    [ 'tx', 'ty', 'sx', 'sy', 'sz', 'v' ] ] )

                # Hoof
                guideList.append( [ 'HoofBack_Guide', 'HoofBack_Lft_Jnt', 'PasternBack_Guide', justTzRx ] )

                # Hoof Tip
                guideList.append( [ 'HoofBackTip_Guide', 'HoofBackTip_Lft_Jnt', 'HoofBack_Guide', justTzRx ] )

                # Tail
                guideList.append( [ 'Tail1_Guide', 'Tail1_Jnt', 'Pelvis_Guide', attrList ] )
                guideList.append( [ 'Tail2_Guide', 'Tail12_Jnt', 'Tail1_Guide', attrList ] )
                # guideList.append( ['Tail1_Guide', 'Tail1_Jnt', 'Pelvis_Guide', attrList] )

                # Shoulder
                guideList.append( [ 'Shoulder_Guide', 'Shoulder_Jnt', 'Pelvis_Guide', attrList ] )

                # Spine
                guideList.append( [ 'Spine1_Guide', 'Spine1_Jnt', 'Pelvis_Guide', attrList ] )
                guideList.append( [ 'Spine2_Guide', 'Spine6_Jnt', 'Shoulder_Guide', attrList ] )

                # Head
                guideList.append( [ 'Head_Guide', 'Head_Jnt', 'Shoulder_Guide', justTzRx ] )

                # Neck 1
                guideList.append( [ 'Neck1_Guide', 'Neck1_Jnt', 'Shoulder_Guide', attrList ] )

                # Neck 2
                guideList.append( [ 'Neck2_Guide', 'Neck8_Jnt', 'Head_Guide', attrList ] )

                # HeadTip
                guideList.append( [ 'HeadTip_Guide', 'HeadTip_Jnt', 'Head_Guide', justTzRx ] )

                # Jaw
                guideList.append( [ 'Jaw_Guide', 'Jaw_Jnt', 'Head_Guide', attrList ] )

                # JawTip
                guideList.append( [ 'JawTip_Guide', 'JawTip_Jnt', 'Jaw_Guide', attrList ] )

                # Eyes
                guideList.append( [ 'Eye_Lft_Guide', 'Eye_Lft_Jnt', 'Head_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Ear
                guideList.append( [ 'Ear_Lft_Guide', 'Ear_Lft_Jnt', 'Head_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # EarTip
                guideList.append( [ 'EarTip_Lft_Guide', 'EarTip_Lft_Jnt', 'Ear_Lft_Guide', attrList ] )

                # Scapula
                guideList.append(
                    [ 'Scapula_Lft_Guide', 'Scapula_Lft_Jnt', 'Shoulder_Guide', [ 'sx', 'sy', 'sz', 'v' ] ] )

                # Humerus
                guideList.append( [ 'Humerus_Lft_Guide', 'Humerus_Lft_Jnt', 'Scapula_Lft_Guide', justTzRx ] )

                # Radius
                guideList.append( [ 'Radius_Lft_Guide', 'Radius_Lft_Jnt', 'Humerus_Lft_Guide', justTzRx ] )

                # CannonFront
                guideList.append( [ 'CannonFront_Lft_Guide', 'CannonFront_Lft_Jnt', 'Radius_Lft_Guide', justTzRx ] )

                # CannonFront
                guideList.append(
                    [ 'PasternFront_Lft_Guide', 'PasternFront_Lft_Jnt', 'CannonFront_Lft_Guide', justTzRx ] )

                # HoofFront
                guideList.append(
                    [ 'HoofFront_Lft_Guide', 'HoofFront_Lft_Jnt', 'PasternFront_Lft_Guide', justTzRx ] )

                # HoofFrontTip
                guideList.append(
                    [ 'HoofFrontTip_Lft_Guide', 'HoofFrontTip_Lft_Jnt', 'HoofFront_Lft_Guide', justTzRx ] )

                for guide in guideList:
                    ctrlDict[ 'name' ] = guide[ 0 ]
                    ctrlDict[ 'matchTransform' ] = guide[ 1 ]
                    if guide[ 2 ] in guideDict:
                        ctrlDict[ 'parent' ] = guideDict[ guide[ 2 ] ][ 0 ]
                    else:
                        ctrlDict[ 'parent' ] = guide[ 2 ]

                    guideDict[ ctrlDict[ 'name' ] ] = self.create_handle( **ctrlDict )
                    self.swap_rotation_with_parent( guideDict[ ctrlDict[ 'name' ] ])
                    self.lock_attrs( guideDict[ ctrlDict[ 'name' ] ], guide[ 3 ] )
                    self.set_metaData( self.find_node( charRoot, guideDict[ ctrlDict[ 'name' ] ] ), data )

                # Spine
                src = 'Spine1_Guide'
                dst = 'Spine2_Guide'
                spine = self.create_spline_simple( 'spine', src, dst, 4, [ 90, 0, 0 ], 5 )

                for i in range( 4 ):
                    mc.parentConstraint( spine[ 2 ][ i ], 'Spine' + str( i + 2 ) + '_Jnt' )

                mc.parent( spine[ 0 ], 'Guides_Body_Grp' )

                # Neck
                src = 'Neck1_Guide'
                dst = 'Neck2_Guide'
                neck = self.create_spline_simple( 'neck', src, dst, 6, [ 90, 0, 0 ], 5 )

                for i in range( 6 ):
                    mc.parentConstraint( neck[ 2 ][ i ], 'Neck' + str( i + 2 ) + '_Jnt' )

                mc.parent( neck[ 0 ], 'Guides_Body_Grp' )

                # Tail
                src = 'Tail1_Guide'
                dst = 'Tail2_Guide'
                tail = self.create_spline_simple( 'tail', src, dst, 10, [ -90, 0, 0 ], 5 )

                for i in range( 10 ):
                    mc.parentConstraint( tail[ 2 ][ i ], 'Tail' + str( i + 2 ) + '_Jnt' )

                mc.parent( tail[ 0 ], 'Guides_Body_Grp' )

                return True

    def build_constraints( self, rootNode, type ):

        offset = om.MEulerRotation( math.radians( 180.0 ), 0.0, 0.0, 0 ).asMatrix()
        proxy_grp = self.find_node(rootNode, 'Proxy_Grp')
        if type == kBipedUE:

            GUIDE_SIDE = ['Lft', 'Rgt']
            UP_VEC = ['Shoulder', 'Hips']
            HAND = ['hand','foot']

            # create misc. constraints for the twist joints in arms and legs
            for i, SIDE in enumerate(['l','r']):

                multi = 1
                if SIDE == 'r':
                    multi=-1

                for j, LIMB in enumerate(['arm', 'leg']):

                    if LIMB == 'arm':
                        front_multi = 1
                        upperarm =  'upperarm'
                        lowerarm = 'lowerarm'
                    else:
                        front_multi = -1
                        upperarm = 'thigh'
                        lowerarm = 'calf'

                    up = mc.createNode('transform', name=UP_VEC[j]+'_'+GUIDE_SIDE[i]+'_upVec', p=proxy_grp, ss=True)
                    guide = self.find_node(rootNode, UP_VEC[j]+'_'+GUIDE_SIDE[i]+'_upVec_Guide')
                    mc.parentConstraint(guide, up)

                    uparm = self.find_node(rootNode, upperarm+'_'+SIDE)
                    loarm = self.find_node(rootNode, lowerarm+'_'+SIDE)
                    hand = self.find_node(rootNode, HAND[j]+'_'+SIDE)

                    prx_uparm = mc.createNode('transform', name=upperarm+'_prx_01_'+SIDE, p=proxy_grp, ss=True)
                    prx_loarm = mc.createNode('transform', name=lowerarm+'_prx_01_'+SIDE, p=prx_uparm, ss=True)
                    prx_hand = mc.createNode('transform', name=HAND[j]+'_prx_01_'+SIDE, p=prx_loarm, ss=True)

                    mc.parentConstraint(uparm, prx_uparm)
                    mc.parentConstraint(loarm, prx_loarm)
                    mc.parentConstraint(hand, prx_hand)

                    prx_upvec_loarm = mc.createNode('transform', name=lowerarm+'_prx_upvec_01_'+SIDE, p=prx_loarm, ss=True)
                    mc.setAttr( prx_upvec_loarm + '.t', 0,0,5*front_multi )

                    prx_upvec_hand = mc.createNode('transform', name=HAND[j]+'_prx_upvec_01_'+SIDE, p=prx_hand, ss=True)
                    mc.setAttr( prx_upvec_hand + '.t', 0,0,5*front_multi )

                    uparm_prx_1 = mc.createNode('transform', name=upperarm+'_twist_prx_01_'+SIDE, p=prx_uparm, ss=True)
                    guide = self.find_node(rootNode, upperarm+'_twist_01_'+SIDE)
                    mc.pointConstraint(guide, uparm_prx_1)

                    uparm_prx_2 = mc.createNode('transform', name=upperarm+'_twist_prx_02_'+SIDE, p=prx_uparm, ss=True)
                    guide = self.find_node(rootNode, upperarm+'_twist_02_'+SIDE)
                    mc.pointConstraint(guide, uparm_prx_2)

                    loarm_prx_1 = mc.createNode('transform', name=lowerarm+'_twist_prx_01_'+SIDE, p=prx_loarm, ss=True)
                    guide = self.find_node(rootNode, lowerarm+'_twist_01_'+SIDE)
                    mc.pointConstraint(guide, loarm_prx_1)

                    loarm_prx_2 = mc.createNode('transform', name=lowerarm+'_twist_prx_02_'+SIDE, p=prx_loarm, ss=True)
                    guide = self.find_node(rootNode, lowerarm+'_twist_02_'+SIDE)
                    mc.pointConstraint(guide, loarm_prx_2)

                    upVec = (0, 0, 1 * multi * front_multi)


                    aimVec = (1*multi*front_multi, 0, 0)

                    mc.aimConstraint(prx_loarm, uparm_prx_2, aim=aimVec, upVector=upVec, wut='object', wuo=up)

                    aimVec = (-1*multi*front_multi, 0, 0)

                    upVec = (0, 0, 1*front_multi)
                    mc.aimConstraint(prx_uparm, uparm_prx_1, aim=aimVec, upVector=upVec, wut='object', wuo=prx_upvec_loarm)

                    target = self.find_node(rootNode, upperarm+'_twist_01_'+SIDE)
                    pb1 = self.create_pair_blend( target, uparm_prx_1, kPairBlendRotate, 0.5 )

                    target = self.find_node(rootNode, upperarm+'_twist_02_'+SIDE)
                    pb2 = self.create_pair_blend( target, uparm_prx_2, kPairBlendRotate, 0.5 )

                    mc.connectAttr( pb1 + '.outRotate', pb2 + '.inRotate2', f = True )

                    # Lower Arm
                    aimVec = (-1*multi*front_multi, 0, 0)
                    upVec = (0, 0, -1*front_multi)
                    '''
                    if LIMB == 'arm':
                        upVec = (0, 1, 0)
                    else:
                        upVec = (0, 0, 1*front_multi)
                    '''
                    mc.aimConstraint(prx_loarm, loarm_prx_1, aim=aimVec, upVector=upVec, wut='object', wuo=prx_upvec_hand)

                    target1 = self.find_node(rootNode, lowerarm+'_twist_01_'+SIDE)
                    mc.orientConstraint( loarm_prx_1 , target1 )

                    target2 = self.find_node(rootNode, lowerarm+'_twist_02_'+SIDE)
                    blend = self.create_pair_blend( target2, target1, kPairBlendRotate, 0.5 )

            mc.parentConstraint( self.find_node( rootNode, 'foot_l' ), self.find_node( rootNode, 'ik_foot_l'   ), mo=True )
            mc.parentConstraint( self.find_node( rootNode, 'foot_r' ), self.find_node( rootNode, 'ik_foot_r'   ), mo=True )
            mc.parentConstraint( self.find_node( rootNode, 'hand_r' ), self.find_node( rootNode, 'ik_hand_gun' ), mo=True )
            mc.parentConstraint( self.find_node( rootNode, 'hand_l' ), self.find_node( rootNode, 'ik_hand_l'   ), mo=True )

        if type == kBiped:
            ##################################################################################################
            #
            # Constraints

            aim = self.find_node( rootNode, 'ArmUp_Aux1_Lft_Jnt' )
            target = self.find_node( rootNode, 'ArmLo_Lft_Jnt' )
            up = self.find_node( rootNode, 'Shoulder_Lft_upVec' )
            aimVec = (1, 0, 0)
            upVec = (0, 1, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'ArmLo_Aux3_Lft_Jnt' )
            target = self.find_node( rootNode, 'ArmLo_Lft_Jnt' )
            up = self.find_node( rootNode, 'Hand_Lft_upVec' )
            aimVec = (-1, 0, 0)
            upVec = (0, 0, 1)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegUp_Aux1_Lft_Jnt' )
            target = self.find_node( rootNode, 'LegUp_Lft_Jnt' )
            up = self.find_node( rootNode, 'Hips_Lft_upVec' )
            aimVec = (0, 1, 0)
            upVec = (1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegUp_Aux1_Lft_Jnt' )
            target = self.find_node( rootNode, 'LegUp_Lft_Jnt' )
            up = self.find_node( rootNode, 'Hips_Lft_upVec' )
            aimVec = (0, 1, 0)
            upVec = (1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegLo_Aux3_Lft_Jnt' )
            target = self.find_node( rootNode, 'Foot_Lft_Jnt' )
            up = self.find_node( rootNode, 'Ankle_Lft_upVec' )
            aimVec = (0, -1, 0)
            upVec = (1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'ArmUp_Aux1_Rgt_Jnt' )
            target = self.find_node( rootNode, 'ArmLo_Rgt_Jnt' )
            up = self.find_node( rootNode, 'Shoulder_Rgt_upVec' )
            aimVec = (-1, 0, 0)
            upVec = (0, -1, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'ArmLo_Aux3_Rgt_Jnt' )
            target = self.find_node( rootNode, 'ArmLo_Rgt_Jnt' )
            up = self.find_node( rootNode, 'Hand_Rgt_upVec' )
            aimVec = (1, 0, 0)
            upVec = (0, 0, -1)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegUp_Aux1_Rgt_Jnt' )
            target = self.find_node( rootNode, 'LegUp_Rgt_Jnt' )
            up = self.find_node( rootNode, 'Hips_Rgt_upVec' )
            aimVec = (0, -1, 0)
            upVec = (-1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegUp_Aux1_Rgt_Jnt' )
            target = self.find_node( rootNode, 'LegUp_Rgt_Jnt' )
            up = self.find_node( rootNode, 'Hips_Rgt_upVec' )
            aimVec = (0, -1, 0)
            upVec = (-1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            aim = self.find_node( rootNode, 'LegLo_Aux3_Rgt_Jnt' )
            target = self.find_node( rootNode, 'Foot_Rgt_Jnt' )
            up = self.find_node( rootNode, 'Ankle_Rgt_upVec' )
            aimVec = (0, 1, 0)
            upVec = (-1, 0, 0)
            mc.aimConstraint( target, aim, aim = aimVec, upVector = upVec, wut = 'object', wuo = up )

            # Constraints
            #
            ##################################################################################################


        if type == kQuadruped:
            pass

        return True

    def build_main_attrs(self, rootGrp ):

        for attrName in ['globalScale', 'globalCtrlScale', 'jointRadius']:
            if not mc.attributeQuery(attrName, node=rootGrp, exists=True):
                mc.addAttr(rootGrp, longName=attrName, defaultValue=1, at='float')
                mc.setAttr(rootGrp + '.' + attrName, k=True)

        dispDict = {
            'Rig_Grp': 'show_Rig',
            'Joint_Grp': 'show_Joints',
            'Guides_Grp': 'show_Guides',
            'Geo_Grp': 'show_Geo',
            'Mocap_Grp': 'show_Mocap'
        }
        for key in dispDict.keys():
            jntGrp = self.find_node(rootGrp, key)
            if jntGrp:
                if mc.objExists(jntGrp):
                    attrName = dispDict[key]
                    if not mc.attributeQuery(attrName, node=rootGrp, exists=True):
                        mc.addAttr(rootGrp, longName=attrName, enumName='off:on', defaultValue=0, at='enum')
                        mc.setAttr(rootGrp + '.' + attrName, k=True)
                        if key == 'Geo_Grp':
                            mc.setAttr( rootGrp + '.' + attrName, True )

                        mc.setAttr(jntGrp + '.v', lock=False)
                        mc.connectAttr(rootGrp + '.' + attrName, jntGrp + '.v', force=True)

        dispDict = {
            'Geo_Grp': 'display_Geo',
            'Joint_Grp': 'display_Joint',
        }

        for key in dispDict.keys():
            geoGrp = self.find_node(rootGrp, key)
            if geoGrp:
                if mc.objExists(geoGrp):
                    try:
                        mc.setAttr(geoGrp + '.overrideEnabled', 1)
                    except:
                        pass
                    attrName = dispDict[key]
                    if not mc.attributeQuery(attrName, node=rootGrp, exists=True):
                        mc.addAttr(rootGrp, longName=attrName, enumName='Normal:Template:Reference', defaultValue=2,
                                   at='enum')
                        mc.setAttr(rootGrp + '.' + attrName, k=True)
                    try:
                        if not mc.isConnected(rootGrp + '.' + attrName, geoGrp + '.overrideDisplayType'):
                            mc.connectAttr(rootGrp + '.' + attrName, geoGrp + '.overrideDisplayType', force=True)
                    except:
                        pass

    def build_main_grps( self, *args ):

        char = 'Adam'
        type = kBiped

        if len(args) == 2:
            char = args[0]
            type = args[1]

        if mc.objExists(char):

            count = 1
            newChar = char + str(count)
            while mc.objExists(newChar):
                newChar = char + str(count)
                count += 1
            char = newChar

        rootGrp = mc.createNode('transform', name=char, ss=True)
        transformGrp = mc.createNode('transform', name='Transform_Grp', ss=True, parent=rootGrp)
        cnstGrp = mc.createNode('transform', name='Cnst_Grp', ss=True, parent=transformGrp)
        offsetGrp = mc.createNode('transform', name='Offset_Grp', ss=True, parent=cnstGrp)

        geoGrp = mc.createNode('transform', name='Geo_Grp', ss=True, parent=offsetGrp)
        mc.setAttr(geoGrp + '.inheritsTransform', 0)

        jointGrp = mc.createNode('transform', name='Joint_Grp', ss=True, parent=offsetGrp)
        rigGrp = mc.createNode('transform', name='Rig_Grp', ss=True, parent=offsetGrp)
        mc.setAttr(rigGrp + '.hideOnPlayback', 1)
        mocapGrp = mc.createNode('transform', name='Mocap_Grp', ss=True, parent=offsetGrp)

        rigGrp = mc.createNode('transform', name='Guides_Grp', ss=True, parent=offsetGrp)

        data = {'Type': kBipedRoot, 'RigType': type}
        self.set_metaData(rootGrp, data)

        self.build_main_attrs( rootGrp )

        # Display Type for Geo Grp

        # Lock attributes
        self.lock_attrs(rootGrp, ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'])

        return {'Main': rootGrp, 'Geo': geoGrp, 'Joint': jointGrp, 'Rig': rigGrp, 'Mocap': mocapGrp}

    def get_hik_data(self,type = kBiped ):

        SIDE=['Lft', 'Rgt']
        SIDELONG=['Left', 'Right']

        hikNodes = {}
        if type == kBiped:
            hikNodes['Reference'] = {'Matrix': 'Main_Ctr_Ctrl', 'Parent': None, 'Ctrls': ['Main_Ctr_Ctrl']}
            hikNodes['Hips'] = {'Matrix': 'Hips_Ctr_Ctrl', 'Parent': 'Reference',
                                'Ctrls': ['Hips_Ctr_Ctrl', 'Torso_Ctr_Ctrl']}
            hikNodes['Spine'] = {'Matrix': 'Spine1_Ctr_Ctrl', 'Parent': 'Hips', 'Ctrls': ['Spine1_Ctr_Ctrl']}
            hikNodes['Spine1'] = {'Matrix': 'Spine2_Ctr_Ctrl', 'Parent': 'Spine', 'Ctrls': ['Spine2_Ctr_Ctrl']}
            hikNodes['Spine2'] = {'Matrix': 'Spine3_Ctr_Ctrl', 'Parent': 'Spine1', 'Ctrls': ['Spine3_Ctr_Ctrl']}

            hikNodes['Spine3'] = {'Matrix': 'Chest_Ctr_Ctrl', 'Parent': 'Spine2', 'Ctrls': ['Chest_Ctr_Ctrl']}
            hikNodes['Neck'] = {'Matrix': 'Neck_Ctr_Ctrl', 'Parent': 'Spine3', 'Ctrls': ['Neck_Ctr_Ctrl']}

            hikNodes['Head'] = {'Matrix': 'Head_Ctr_Ctrl', 'Parent': 'Neck', 'Ctrls': ['Head_Ctr_Ctrl']}

            hikNodes['LeftUpLeg'] = {'Matrix': 'LegUp_Lft_Guide', 'Parent': 'Hips', 'Ctrls': []}
            hikNodes['LeftLeg'] = {'Matrix': 'LegLo_Lft_Guide', 'Parent': 'LeftUpLeg', 'Ctrls': ['LegPole_IK_Lft_Ctrl']}
            hikNodes['LeftFoot'] = {'Matrix': 'Foot_Lft_Guide', 'Parent': 'LeftLeg',
                                    'Ctrls': ['Foot_IK_Lft_Ctrl', 'Heel_IK_Lft_Ctrl', 'FootLift_IK_Lft_Ctrl']}
            hikNodes['LeftToeBase'] = {'Matrix': 'Toes_IK_Lft_Ctrl', 'Parent': 'LeftFoot',
                                       'Ctrls': ['Toes_IK_Lft_Ctrl', 'ToesTip_IK_Lft_Ctrl']}

            hikNodes['RightUpLeg'] = {'Matrix': 'LegUp_Rgt_Guide', 'Parent': 'Hips', 'Ctrls': []}
            hikNodes['RightLeg'] = {'Matrix': 'LegLo_Rgt_Guide', 'Parent': 'RightUpLeg', 'Ctrls': ['LegPole_IK_Rgt_Ctrl']}
            hikNodes['RightFoot'] = {'Matrix': 'Foot_Rgt_Guide', 'Parent': 'RightLeg',
                                     'Ctrls': ['Foot_IK_Rgt_Ctrl', 'Heel_IK_Rgt_Ctrl', 'FootLift_IK_Rgt_Ctrl']}
            hikNodes['RightToeBase'] = {'Matrix': 'Toes_IK_Rgt_Ctrl', 'Parent': 'RightFoot',
                                        'Ctrls': ['Toes_IK_Rgt_Ctrl', 'ToesTip_IK_Rgt_Ctrl']}

            hikNodes['LeftShoulder'] = {'Matrix': 'Clavicle_Lft_Ctrl', 'Parent': 'Spine3', 'Ctrls': ['Clavicle_Lft_Ctrl']}
            hikNodes['LeftArm'] = {'Matrix': 'ArmUp_FK_Lft_Ctrl', 'Parent': 'LeftShoulder', 'Ctrls': ['ArmUp_FK_Lft_Ctrl']}
            hikNodes['LeftForeArm'] = {'Matrix': 'ArmLo_FK_Lft_Ctrl', 'Parent': 'LeftArm', 'Ctrls': ['ArmLo_FK_Lft_Ctrl']}
            hikNodes['LeftHand'] = {'Matrix': 'Hand_FK_Lft_Ctrl', 'Parent': 'LeftForeArm', 'Ctrls': ['Hand_FK_Lft_Ctrl']}
            hikNodes['LeftFingerBase'] = {'Matrix': 'Palm_Lft_Jnt', 'Parent': 'LeftHand', 'Ctrls': []}

            hikNodes['RightShoulder'] = {'Matrix': 'Clavicle_Rgt_Ctrl', 'Parent': 'Spine3', 'Ctrls': ['Clavicle_Rgt_Ctrl']}
            hikNodes['RightArm'] = {'Matrix': 'ArmUp_FK_Rgt_Ctrl', 'Parent': 'RightShoulder',
                                    'Ctrls': ['ArmUp_FK_Rgt_Ctrl']}
            hikNodes['RightForeArm'] = {'Matrix': 'ArmLo_FK_Rgt_Ctrl', 'Parent': 'RightArm', 'Ctrls': ['ArmLo_FK_Rgt_Ctrl']}
            hikNodes['RightHand'] = {'Matrix': 'Hand_FK_Rgt_Ctrl', 'Parent': 'RightForeArm', 'Ctrls': ['Hand_FK_Rgt_Ctrl']}
            hikNodes['RightFingerBase'] = {'Matrix': 'Palm_Rgt_Jnt', 'Parent': 'RightHand', 'Ctrls': []}

        elif type == kBipedUE:

            hikNodes['root']  = {'Matrix': 'Main_Ctr_Ctrl', 'Parent': None, 'Ctrls': ['Main_Ctr_Ctrl']}
            hikNodes['pelvis']       = {'Matrix': 'Hips_Guide', 'Parent': 'root',
                                      'Ctrls': ['Hips_Ctr_Ctrl', 'Torso_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['spine_01']      = {'Matrix': 'Spine1_Guide', 'Parent': 'pelvis', 'Ctrls': ['Spine1_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['spine_02']     = {'Matrix': 'Spine2_Guide', 'Parent': 'spine_01', 'Ctrls': ['Spine2_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['spine_03']     = {'Matrix': 'Spine3_Guide', 'Parent': 'spine_02', 'Ctrls': ['Spine3_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['spine_04']     = {'Matrix': 'Spine4_Guide', 'Parent': 'spine_03', 'Ctrls': ['Spine4_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['spine_05']     = {'Matrix': 'Spine5_Guide', 'Parent': 'spine_04', 'Ctrls': ['Spine5_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}

            hikNodes['neck_01']       = {'Matrix': 'Neck1_Ctr_Ctrl', 'Parent': 'spine_05', 'Ctrls': ['Neck1_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['neck_02']      = {'Matrix': 'Neck2_Ctr_Ctrl', 'Parent': 'neck_01', 'Ctrls': ['Neck2_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}

            hikNodes['head']       = {'Matrix': 'Head_Ctr_Ctrl', 'Parent': 'neck_02', 'Ctrls': ['Head_Ctr_Ctrl'],
                                      'RotOffset':[-90,0,90]}

            hikNodes['thigh_l']  = {'Matrix': 'LegUp_Lft_Guide', 'Parent': 'pelvis', 'Ctrls': [],
                                      'RotOffset':[-90,0,90]}
            hikNodes['calf_l']    = {'Matrix': 'LegLo_Lft_Guide', 'Parent': 'thigh_l', 'Ctrls': ['LegPole_IK_Lft_Ctrl'],
                                      'RotOffset':[-90,0,90]}
            hikNodes['foot_l']   = {'Matrix': 'Foot_Lft_Guide', 'Parent': 'calf_l',
                                      'Ctrls': ['Foot_IK_Lft_Ctrl', 'Heel_IK_Lft_Ctrl', 'FootLift_IK_Lft_Ctrl']}
            hikNodes['ball_l'] = {'Matrix': 'Toes_IK_Lft_Ctrl', 'Parent': 'foot_l',
                                       'Ctrls': ['Toes_IK_Lft_Ctrl', 'ToesTip_IK_Lft_Ctrl']}

            hikNodes['thigh_r'] = {'Matrix': 'LegUp_Rgt_Guide', 'Parent': 'pelvis', 'Ctrls': []}
            hikNodes['calf_r']   = {'Matrix': 'LegLo_Rgt_Guide', 'Parent': 'thigh_r', 'Ctrls': ['LegPole_IK_Rgt_Ctrl']}
            hikNodes['foot_r']  = {'Matrix': 'Foot_Rgt_Guide', 'Parent': 'calf_r',
                                      'Ctrls': ['Foot_IK_Rgt_Ctrl', 'Heel_IK_Rgt_Ctrl', 'FootLift_IK_Rgt_Ctrl']}
            hikNodes['ball_r'] = {'Matrix': 'Toes_IK_Rgt_Ctrl', 'Parent': 'foot_r',
                                        'Ctrls': ['Toes_IK_Rgt_Ctrl', 'ToesTip_IK_Rgt_Ctrl']}

            hikNodes['clavicle_l']   = {'Matrix': 'Clavicle_Lft_Ctrl', 'Parent': 'spine_05', 'Ctrls': ['Clavicle_Lft_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['upperarm_l']        = {'Matrix': 'ArmUp_FK_Lft_Ctrl', 'Parent': 'clavicle_l', 'Ctrls': ['ArmUp_FK_Lft_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['lowerarm_l']    = {'Matrix': 'ArmLo_FK_Lft_Ctrl', 'Parent': 'upperarm_l', 'Ctrls': ['ArmLo_FK_Lft_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['hand_l']       = {'Matrix': 'Hand_FK_Lft_Ctrl', 'Parent': 'lowerarm_l', 'Ctrls': ['Hand_FK_Lft_Ctrl'],
                                      'RotOffset':[180,0,0]}

            hikNodes['clavicle_r']  = {'Matrix': 'Clavicle_Rgt_Ctrl', 'Parent': 'spine_05', 'Ctrls': ['Clavicle_Rgt_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['upperarm_r']       = {'Matrix': 'ArmUp_FK_Rgt_Ctrl', 'Parent': 'clavicle_r', 'Ctrls': ['ArmUp_FK_Rgt_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['lowerarm_r']   = {'Matrix': 'ArmLo_FK_Rgt_Ctrl', 'Parent': 'upperarm_r', 'Ctrls': ['ArmLo_FK_Rgt_Ctrl'],
                                      'RotOffset':[-90,0,0]}
            hikNodes['hand_r']       = {'Matrix': 'Hand_FK_Rgt_Ctrl', 'Parent': 'lowerarm_r', 'Ctrls': ['Hand_FK_Rgt_Ctrl'],
                                      'RotOffset':[-90,0,0]}

            #hikNodes['LeftHandThumb1']       = {'Matrix': 'Thumb1_Lft_Ctrl', 'Parent': 'LeftHand', 'Ctrls': ['Thumb1_Lft_Ctrl']}
            #hikNodes['LeftHandThumb2']       = {'Matrix': 'Thumb2_Lft_Ctrl', 'Parent': 'LeftHandThumb1', 'Ctrls': ['Thumb2_Lft_Ctrl']}
            #hikNodes['LeftHandThumb3']       = {'Matrix': 'Thumb3_Lft_Ctrl', 'Parent': 'LeftHandThumb2', 'Ctrls': ['Thumb3_Lft_Ctrl']}

            '''
            for i in range(2):

                for finger in ['Index', 'Middle', 'Ring', 'Pinky']:

                    hikNodes[SIDELONG[i]+'InHand'+finger] = {
                        'Matrix': finger+'Meta_'+SIDE[i]+'_Ctrl',
                        'Parent': SIDELONG[i]+'Hand',
                        'Ctrls': [finger+'Meta_'+SIDE[i]+'_Ctrl']
                    }

                    for j in range(1,4):
                        index = str(j)
                        if j == 1:
                            parent = SIDELONG[i]+'InHand'+finger
                        else:
                            parent = SIDELONG[i]+finger+str(j-1)
                        offset =  [-90,0,0]
                        hikNodes[SIDELONG[i]+'Hand'+finger+index] = {
                            'Matrix': finger+index+'_'+SIDE[i]+'_Ctrl',
                            'Parent': parent,
                            'Ctrls': [finger+index+'_'+SIDE[i]+'_Ctrl'],
                            'RotOffset': offset}

                finger = 'Thumb'
                for j in range(1,4):
                    index = str(j)
                    if j == 1:
                        parent = SIDELONG[i]+'Hand'
                    else:
                        parent = SIDELONG[i]+'Hand'+finger+str(j-1)

                    hikNodes[SIDELONG[i]+'Hand'+finger+index] = {
                        'Matrix': finger+index+'_'+SIDE[i]+'_Ctrl',
                        'Parent': parent,
                        'Ctrls': [finger+index+'_'+SIDE[i]+'_Ctrl']}
                    print(SIDELONG[i]+'Hand'+finger+index, parent)

            '''
        return hikNodes

    def build_mocap( self, *args ):

        if args:
            char = args[0]
            type = args[1]

        if char is None:
            char = self.get_active_char()

        if char is None:
            mc.warning( 'aniMeta: No character specified, aborting mocap build.')
            return False
        # Create Main Groups
        #mainGrp = self.build_main_grps( char )

        rigNodes = {}
        hikJoints = {}
        prefix = 'hik:'
        suffix = '_Jnt'
        if type == kBipedUE:
            suffix = ''
        charName = 'hik_' + char

        offset_grp = self.find_node( char, 'Offset_Grp' )
        mocap_grp = self.find_node( char, 'Mocap_Grp' )

        if mocap_grp is None:
            mocap_grp = mc.createNode('transform', name='Mocap_Grp', ss=True, parent=offset_grp)

        ####################################################
        #
        # Create HIK Skeleton

        hikNodes = self.get_hik_data(type)

        joints = []

        # Create Joints
        for key in hikNodes.keys():
            joint = mc.createNode( 'joint',
                                    name=prefix + key + suffix,
                                    ss=True,
                                    parent=mocap_grp )
            joints.append( joint )
            hikNodes[key]['Joint'] = self.short_name( joint )

            node  = self.find_node( char, hikNodes[key]['Matrix'] )       # find the node

            if node:

                m = self.get_matrix( node )   # get the transformation


                if not isinstance( m, om.MMatrix ):
                    mc.confirmDialog( m=node )

                if 'RotOffset' in hikNodes[key]:
                    rx = hikNodes[key]['RotOffset'][0]
                    ry = hikNodes[key]['RotOffset'][1]
                    rz = hikNodes[key]['RotOffset'][2]
                    offset = om.MEulerRotation( math.radians( rx ), math.radians(ry), math.radians(rz))
                    rot_offset = self.create_matrix(rotate=offset)
                    m = rot_offset * m

                self.set_matrix( joint, m  )   # set the transformation

            else:
                mc.warning( 'aniMeta build mocap: Can not find node  ' +  hikNodes[key]['Matrix'] )


        mocap_grp  = self.find_node( char, 'Mocap_Grp' )
        joint_grp  = self.find_node( char, 'Joint_Grp' )

        # Parent Joints
        for key in hikNodes.keys():

            if hikNodes[key]['Parent'] is not None:

                joint  = hikNodes[key]['Joint']
                parent = prefix + hikNodes[key]['Parent'] + suffix

                joint  = self.find_node( mocap_grp,  joint )
                parent = self.find_node( mocap_grp,  parent ) # find the node

                m = self.get_matrix( joint, kWorld)

                joint = mc.parent(joint, parent)[0]
                if type == kBipedUE:
                    mc.setAttr(joint+'.jointOrient', 0,0,0)
                    self.set_matrix(joint,m)



        pairBlendTR = ['Hips', 'Reference', 'RightFoot', 'LeftFoot', 'LeftToeBase', 'RightToeBase']
        if type == kBipedUE:
            pairBlendTR = ['pelvis', 'root', 'foot_l', 'foot_r', 'ball_l', 'ball_r']

        # Create Blend Constraints
        for key in hikNodes.keys():
            if 'Ctrls' in hikNodes[key]:
                ctrls = hikNodes[key]['Ctrls']
                if ctrls is not None:
                    if len(ctrls) > 0:
                        for ctrl in ctrls:

                            node = self.find_node( char, ctrl )  # find the node
                            ctrl_parent = mc.listRelatives( node, p=True, pa=True )
                            if ctrl_parent is not None:

                                if 'Blnd' in ctrl_parent[0]:
                                    hikNodes[key]['Ctrl_Blnd_Grp'] = ctrl_parent[0]
                                else:
                                    ctrl_parent = mc.listRelatives( ctrl_parent[0], p=True, pa=True )
                                    if 'Blnd' in ctrl_parent[0]:
                                        hikNodes[key]['Ctrl_Blnd_Grp'] = ctrl_parent[0]
                                    else:
                                        mc.warning( 'AniMeta create mocap: '+ node + ' has no blend grp.')

                                ctrl_parent = mc.listRelatives( ctrl_parent[0] , p=True, pa=True)[0]

                                hikNodes[key]['Ctrl_Parent'] = ctrl_parent
                                hikNodes[key]['Ctrl_Cnst_Grp'] = mc.createNode( 'transform',
                                                                                parent=ctrl_parent,
                                                                                ss=True,
                                                                                name=self.short_name( ctrl ) + '_Cnst_Grp' )

                                # Create Pairblend so we can dial the mocap effect in or out
                                pb = ''

                                if key in pairBlendTR:
                                    pb = self.create_pair_blend( hikNodes[key]['Ctrl_Blnd_Grp'],
                                                                 hikNodes[key]['Ctrl_Cnst_Grp'],
                                                                 kPairBlend,
                                                                 False )
                                else:
                                    pb = self.create_pair_blend( hikNodes[key]['Ctrl_Blnd_Grp'],
                                                                 hikNodes[key]['Ctrl_Cnst_Grp'],
                                                                 kPairBlendRotate,
                                                                 False )

                                # Add Mocap Attribute
                                if not mc.attributeQuery( 'mocap', node=node, exists=True ):
                                    mc.addAttr( node, ln='mocap', min=0, max=1 )
                                    mc.setAttr( node + '.mocap', k=1 )

                                rev = mc.createNode( 'reverse', ss=True, name=self.short_name( ctrl ) + '_Inv' )

                                mc.connectAttr( node + '.mocap', rev + '.ix' )
                                mc.connectAttr( rev  + '.ox',    pb  + '.weight' )

                                #parent = self.find_node( char, hikNodes[key]['Ctrl_Blnd_Grp'] )  # find the node
                                #mc.parent( node, parent )

                                joint    = self.find_node( mocap_grp, hikNodes[key]['Joint'] )  # find the node
                                cnst_grp = self.find_node( char, hikNodes[key]['Ctrl_Cnst_Grp'] )  # find the node

                                mc.parentConstraint( joint, cnst_grp, mo=True )

        # Reset the orientation to get a good T-Pose
        # Is it good for Arm and Leg?
        if type == kBiped:
            for joint in joints:
                if 'RightShoulder' in joint or 'RightUpLeg' in joint:
                    mc.setAttr( joint + '.r', 0,0,0 )
                    mc.setAttr( joint + '.jo', 180,0,0 )
                else:
                    mc.setAttr( joint + '.r', 0,0,0 )
                    mc.setAttr( joint + '.jo', 0,0,0 )
        '''
        elif type == kBipedUE:
            joints = ['Hips', 'Spine', 'Spine1', 'Spine2', 'Spine3', 'Spine4', 'Neck', 'Neck1', 'Head']
            for joint in joints:
                joint_name = 'hik:' + joint + '_Jnt'
                mc.xform(joint_name, ws=True, ro=[0, 0, 0], a=True)

            joints = ['Shoulder', 'Arm', 'ForeArm', 'Hand', 'UpLeg', 'Leg', 'Foot', 'ToeBase']

            for joint in joints:
                joint_name = 'hik:Left' + joint + '_Jnt'
                mc.xform(joint_name, ws=True, ro=[0, 0, 0], a=True)
                joint_name = 'hik:Right' + joint + '_Jnt'
                mc.xform(joint_name, ws=True, ro=[180, 0, 0], a=True)
        '''
        hikCharacter = mc.createNode("HIKCharacterNode", name=char+'_HIK')
        hikProperties = mc.createNode("HIKProperty2State", name=char + "_hikProperties")
        mc.connectAttr(hikProperties + ".message", hikCharacter + ".propertyState")

        for key in hikNodes.keys():

            node = self.find_node(mocap_grp, hikNodes[key]['Joint'] )  # find the node

            exists = mc.attributeQuery('Character', node=node, exists=True)

            if not exists:
                mc.addAttr(node, shortName='ch', longName='Character', attributeType='message')
            try:
                mc.connectAttr( node + '.Character', hikCharacter + '.' + key, f=True)
            except:
                pass

        # This set-up turns off the worldorient attribute if the mocap attribute is activated
        for ctl in ['Head_Ctr_Ctrl', 'ArmUp_FK_Lft_Ctrl', 'ArmUp_FK_Rgt_Ctrl']:

            ctrl = self.find_node( char, ctl )

            if ctrl is not None:
                con = mc.listConnections( ctrl + '.worldOrient', d=True, p=True )

                mc.disconnectAttr( ctrl + '.worldOrient', con[0] )

                rev   = mc.createNode( 'reverse', name=ctl.replace('Ctrl','Rev'), ss=True )
                multi = mc.createNode( 'multiplyDivide', name=ctl.replace('Ctrl','Multi'), ss=True )

                mc.connectAttr( ctrl + '.mocap', rev + '.inputX' )
                mc.connectAttr( rev + '.outputX', multi + '.input1X' )
                mc.connectAttr( ctrl + '.worldOrient', multi + '.input2X' )
                mc.connectAttr( multi + '.outputX' , con[0] )

    def build_pair_blends( self, rootNode, type ):

        if type == kBipedUE:

            for SIDE in [ 'l', 'r' ]:

                #######################################################################
                # Arm

                node = self.find_node( rootNode, 'upperarm_twist_01_' + SIDE  )
                inNode = self.find_node( rootNode, 'lowerarm_' + SIDE  )
                weight = 0.333
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                node = self.find_node( rootNode, 'upperarm_twist_02_' + SIDE  )
                weight = 0.666
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                node = self.find_node( rootNode, 'lowerarm_twist_01_' + SIDE  )
                inNode = self.find_node( rootNode, 'hand_' + SIDE  )
                weight = 0.333
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                node = self.find_node( rootNode, 'lowerarm_twist_02_' + SIDE  )
                weight = 0.666
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # Arm
                #######################################################################

                #######################################################################
                # Leg

                node = self.find_node(rootNode, 'thigh_twist_01_' + SIDE)
                inNode = self.find_node(rootNode, 'calf_' + SIDE)
                weight = 0.333
                mode = kPairBlendTranslate
                self.create_pair_blend(node, inNode, mode, weight)

                node = self.find_node(rootNode, 'thigh_twist_02_' + SIDE)
                weight = 0.666
                mode = kPairBlendTranslate
                self.create_pair_blend(node, inNode, mode, weight)

                node = self.find_node(rootNode, 'calf_twist_01_' + SIDE)
                inNode = self.find_node(rootNode, 'foot_' + SIDE)
                weight = 0.333
                mode = kPairBlendTranslate
                self.create_pair_blend(node, inNode, mode, weight)

                node = self.find_node(rootNode, 'calf_twist_02_' + SIDE)
                weight = 0.666
                mode = kPairBlendTranslate
                self.create_pair_blend(node, inNode, mode, weight)

                # Leg
                #######################################################################

        if type == kBiped:
            # Head
            node = self.find_node( rootNode, 'Head_Jnt_Blend' )
            inNode = self.find_node( rootNode, 'Head_Jnt' )
            mode = kPairBlendRotate
            weight = 0.5
            self.create_pair_blend( node, inNode, mode, weight )

            mc.connectAttr( inNode + '.t', node + '.t' )
            # /Head

            for SIDE in [ 'Lft', 'Rgt' ]:

                #######################################################################
                # Arm

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'ArmUp_Aux3_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'ArmUp_Aux1_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.9
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'ArmLo_' + SIDE + '_Jnt' )
                mc.connectAttr( inNode + '.t', node + '.t', f = True )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'ArmUp_Aux2_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'ArmUp_Aux1_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'ArmLo_' + SIDE + '_Jnt' )
                weight = 0.5
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux1_Lft_Jnt
                node = self.find_node( rootNode, 'ArmUp_Aux1_' + SIDE + '_Jnt' )
                mc.setAttr( node + '.t', 0,0,0 )

                # ArmLo_Blend_Lft_Jnt self.find_node( rootNode, 'Head_Jnt_Blend' )
                mc.connectAttr(
                    self.find_node( rootNode, 'ArmLo_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'ArmLo_Blend_' + SIDE + '_Jnt' ) + '.t',
                    f = True
                )

                mc.connectAttr(
                    self.find_node( rootNode, 'ArmUp_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'Shoulder_Blend_' + SIDE + '_Jnt' ) + '.t',
                    f = True
                )
                mc.connectAttr(
                    self.find_node( rootNode, 'Hand_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'Wrist_Blend_' + SIDE + '_Jnt' ) + '.t',
                    f = True
                )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'ArmLo_Aux1_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'ArmLo_Aux3_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.9
                self.create_pair_blend( node, inNode, mode, weight )
                mc.setAttr( node + '.t', 0,0,0 )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'ArmLo_Aux2_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'ArmLo_Aux3_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'Hand_' + SIDE + '_Jnt' )
                weight = 0.5
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux1_Lft_Jnt
                node = self.find_node( rootNode, 'ArmLo_Aux3_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'Hand_' + SIDE + '_Jnt' )
                mc.connectAttr( inNode + '.t', node + '.t', f = True )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'ArmLo_Blend_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'ArmLo_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'Wrist_Blend_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'Hand_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                # Shoulder_Blend_Lft_Jnt
                node = self.find_node( rootNode, 'Shoulder_Blend_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'Shoulder_Blend_' + SIDE + '_Loc' )
                clav_jnt = self.find_node( rootNode, 'Clavicle_'+SIDE+'_Jnt' )

                soulder_nul = self.create_nul( inNode )

                mc.parentConstraint( clav_jnt, soulder_nul, mo=False )

                mode = kPairBlendRotate
                weight = 0.5
                inNode = self.find_node( rootNode, 'Shoulder_Blend_' + SIDE + '_Loc' )
                self.create_pair_blend( node, inNode, mode, weight )
                mc.orientConstraint(
                    self.find_node( rootNode, 'ArmUp_' + SIDE + '_Jnt' ),
                    self.find_node( rootNode, 'Shoulder_Blend_' + SIDE + '_Loc' ),
                    mo = True
                )

                # Arm
                #
                #######################################################################

                #######################################################################
                #
                # Hand

                fingers = [ 'Thumb', 'Index', 'Middle', 'Ring', 'Pinky' ]
                indices = [ 2, 3, 4 ]

                for finger in fingers:
                    for index in indices:
                        if finger == 'Thumb':
                            index -= 1

                        node = self.find_node( rootNode, finger + str( index ) + '_Blend_' + SIDE + '_Jnt' )
                        inNode = self.find_node( rootNode, finger + str( index ) + '_' + SIDE + '_Jnt' )

                        # Connect Translate
                        mc.connectAttr( inNode + '.t', node + '.t', f = True )

                        # Create Pair Blend
                        mode = kPairBlendRotate
                        weight = 0.5
                        self.create_pair_blend( node, inNode, mode, weight )

                # Hand
                #
                #######################################################################

                #######################################################################
                #
                # Leg

                # LegUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'LegUp_Aux3_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'LegUp_Aux1_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.9
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt' )
                weight = 0.25
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # LegUp_Aux2_Lft_Jnt
                node = self.find_node( rootNode, 'LegUp_Aux2_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'LegUp_Aux1_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt' )
                weight = 0.5
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # LegUp_Aux1_Lft_Jnt
                node = self.find_node( rootNode, 'LegUp_Aux1_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt' )
                weight = 0.75
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # LegLo_Blend_Lft_Jnt
                mc.connectAttr(
                    self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt_Blend' ) + '.t',
                    f = True
                )
                mc.connectAttr(
                    self.find_node( rootNode, 'LegUp_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'LegUp_' + SIDE + '_Jnt_Blend' ) + '.t',
                    f = True
                )
                mc.connectAttr(
                    self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt_Blend' ) + '.t',
                    f = True
                )
                mc.connectAttr(
                    self.find_node( rootNode, 'Toes_' + SIDE + '_Jnt' ) + '.t',
                    self.find_node( rootNode, 'Ball_' + SIDE + '_Jnt_Blend' ) + '.t',
                    f = True
                )

                # LegUp_Aux1_Lft_Jnt
                node = self.find_node( rootNode, 'LegLo_Aux1_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'LegLo_Aux3_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.9
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt' )
                weight = 0.75
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # LegUp_Aux2_Lft_Jnt
                node = self.find_node( rootNode, 'LegLo_Aux2_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'LegLo_Aux3_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                inNode = 'Foot_' + SIDE + '_Jnt'
                weight = 0.5
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # LegUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'LegLo_Aux3_' + SIDE + '_Jnt' )
                inNode = self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt' )
                weight = 0.25
                mode = kPairBlendTranslate
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt_Blend' )
                inNode = self.find_node( rootNode, 'LegLo_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt_Blend' )
                inNode = self.find_node( rootNode, 'Foot_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                # ArmUp_Aux3_Lft_Jnt
                node = self.find_node( rootNode, 'Ball_' + SIDE + '_Jnt_Blend' )
                inNode = self.find_node( rootNode, 'Toes_' + SIDE + '_Jnt' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )

                # Shoulder_Blend_Lft_Jnt
                node = self.find_node( rootNode, 'LegUp_' + SIDE + '_Jnt_Blend' )
                inNode = self.find_node( rootNode, 'Hips_Blend_' + SIDE + '_Loc' )
                mode = kPairBlendRotate
                weight = 0.5
                self.create_pair_blend( node, inNode, mode, weight )
                mc.orientConstraint(
                    self.find_node( rootNode, 'LegUp_' + SIDE + '_Jnt' ),
                    self.find_node( rootNode, 'Hips_Blend_' + SIDE + '_Loc' ),
                    mo = True
                )
                # Leg
                #
                #######################################################################

            # Pair Blends
            #
            ##################################################################################################
        if type == kQuadrupedRoot:
            return True

    def build_scaling( self, rootNode, type ):
        '''
        Deals with setting up the rig in a way that will allow scaling it via the global scale attribute on the Main Grp.
        :param rootNode: The main root node
        :param type: The type of rig, Biped, Quadruped, etc.
        :return: Nothing
        '''

        # Hook up joint radius attrs
        multi = mc.createNode( 'multDoubleLinear', name = 'jointRadiusMulti', ss = True )
        mc.connectAttr( rootNode + '.globalScale', multi + '.input1' )
        mc.connectAttr( rootNode + '.jointRadius', multi + '.input2' )

        joint_grp = self.find_node( rootNode, 'Joint_Grp' )
        rig_grp = self.find_node( rootNode, 'Rig_Grp' )
        guides_grp = self.find_node( rootNode, 'Guides_Grp' )

        if mc.listRelatives( joint_grp, c = True, ad = True, typ = 'joint' , pa=True):
            for jnt in mc.listRelatives( joint_grp, c = True, ad = True, typ = 'joint', pa=True ):
                mc.connectAttr( multi + '.output', jnt + '.radius', f = True )

        # Hook Up global Scale to Control Rig
        mc.connectAttr( rootNode + '.globalScale', rig_grp + '.scaleX' )
        mc.connectAttr( rootNode + '.globalScale', rig_grp + '.scaleY' )
        mc.connectAttr( rootNode + '.globalScale', rig_grp + '.scaleZ' )
        mc.connectAttr( rootNode + '.globalScale', guides_grp + '.scaleX' )
        mc.connectAttr( rootNode + '.globalScale', guides_grp + '.scaleY' )
        mc.connectAttr( rootNode + '.globalScale', guides_grp + '.scaleZ' )

    def create(self, *args, **kwargs):

        char = 'Eve'
        type = kBiped

        if 'char' in kwargs:
            char = kwargs['char']
        if 'type' in kwargs:
            type = kwargs['type']

        print ('\nCreate Rig')

        # Create Main Groups
        mainGrp = self.build_main_grps( char, type )

        rootNode = mainGrp['Main']

        # Get skeleton dictionary
        skeleton = self.get_joints( type )

        # Build skeleton dictionary
        print ('aniMeta: Build Skeleton.')
        self.build_skeleton( skeleton, rootNode )

        # Get aux joint dictionary
        skeleton = self.get_aux_joints( type )

        # Build aux joint
        print ('aniMeta: Build Aux Skeleton.')
        self.build_skeleton( skeleton, rootNode )

        self.hook_up_proxy_transforms( rootNode, type )

        # Create the body guides
        print ('aniMeta: Create the body guides.')
        self.build_body_guides( rootNode, type )

        # Constraints
        print ('aniMeta: Build Constraints.')
        self.build_constraints( rootNode, type )

        # PairBlends
        print ('aniMeta: Build Pair Blends.')
        self.build_pair_blends( rootNode, type )

        # Scale
        print ('aniMeta: Build scaling set-up.')
        self.build_scaling( rootNode, type )

        # Select the new character
        mc.select( rootNode, replace=True)
        mc.setAttr( rootNode + '.show_Joints', 1 )
        mc.setAttr( rootNode + '.show_Guides', True )

        if mc.upAxis(query=True, axis=True) == 'z':
            mc.setAttr( rootNode + '.rx', l=False)
            mc.setAttr( rootNode + '.rx', 90)
            mc.setAttr( rootNode + '.rx', l=True)

        # Refresh the character list
        ui = AniMetaUI( create=False )
        ui.char_list_refresh()
        ui.set_active_char(rootNode)
        print ( 'aniMeta: Guide rig completed.' )

        return rootNode

    def hook_up_proxy_transforms( self, rootNode, type ):

        if type == kBiped:

            for SIDE in ['Lft','Rgt']:

                # Hand Up Vec
                hand_up_vec = self.find_node( rootNode, 'Hand_'+SIDE+'_upVec' )
                hand_jnt = self.find_node( rootNode, 'Hand_'+SIDE+'_Jnt' )
                mc.parentConstraint( hand_jnt, hand_up_vec, mo=True )

                # Leg Up Vec
                foot_up_vec = self.find_node( rootNode, 'Ankle_'+SIDE+'_upVec' )
                foot_jnt = self.find_node( rootNode, 'Foot_'+SIDE+'_Jnt' )
                mc.parentConstraint( foot_jnt, foot_up_vec, mo=True )

    def delete_body_guides( self, *args, **kwargs ):

        charRoot = self.get_active_char()
        deleteOnlyConstraints = False
        if args:
            charRoot = args[0]
        if kwargs:
            if 'deleteOnlyConstraints' in kwargs:
                deleteOnlyConstraints = kwargs['deleteOnlyConstraints']

        delNodes = [ ]
        metaData = None

        if not mc.objExists( charRoot ):
            mc.warning( 'Please select a Biped Root Group.' )
        else:
            metaData = self.get_metaData( charRoot )
            data = { 'Type': kBodyGuide }
            nodes = self.get_nodes( charRoot, data )

            root_jnt = self.find_node( charRoot, 'root' )

            try:
                mc.setAttr( root_jnt + '.overrideEnabled', 0 )
                mc.setAttr( root_jnt + '.overrideDisplayType', 0 )
            except:
                pass
            parents = mc.listRelatives( root_jnt, ad=True, typ='symmetryConstraint', pa=True) or []

            #####################################################################################
            #
            # Store joint positions
            # ... or the positions may be off when the constraints get deleted
            jointDict = self.get_joint_transform( charRoot )

            # Store joint positions
            #
            #####################################################################################

            #####################################################################################
            #
            # Delete Constraints
            for node in nodes:
                node_long = self.find_node( charRoot, node )
                con = mc.listConnections( node_long + '.t', s = True )

                if con:
                    for c in con:
                        if mc.nodeType( c ) == 'parentConstraint' or mc.nodeType( c ) == 'symConstraint':
                            parents.append( c )
            if parents:
                try:
                    if len( parents ) > 0:
                        self.delete_nodes( charRoot, parents )
                except:
                    pass

            if not deleteOnlyConstraints:
                if nodes:
                    try:
                        if len( nodes ) > 0:
                            self.delete_nodes( charRoot, nodes )

                    except:
                        pass
                else:
                    mc.warning('aniMeta: No body guides to delete.')

            for joint in jointDict.keys():
                con = mc.listConnections( joint + '.t', s=1, d=0 )
                if con:
                    if mc.nodeType( con[0] ) == 'symmetryConstraint':
                        mc.delete( con )

            # Delete Constraints
            #
            #####################################################################################

            #####################################################################################
            #
            # Restore joint positions

            self.set_joint_transform( charRoot, jointDict )

            # Restore joint positions
            #
            #####################################################################################

    def delete_controls( self, *args ):

        charRoot = self.get_active_char()

        if args:
            charRoot = args[0]

        delNodes = []

        if not charRoot:
            mc.warning( 'Please select a Biped Root Group.' )
        else:
            rig_grp = self.find_node( charRoot, 'Rig_Grp' )

            if rig_grp is not None:
                # Rig State
                rigState = None
                type = None

                data = self.get_metaData( charRoot )

                if 'RigState' in data:
                    rigState = data[ 'RigState' ]

                if 'Type' in data:
                    type = data[ 'Type' ]

                data[ 'RigState' ] = kRigStateBind

                # Save Control Shape data on Root node
                ctrlDict = { }

                nodes = self.get_nodes( rig_grp, dict = { 'Type': kHandle }, hierarchy = True )

                attrs = [ 'controlSizeX', 'controlSizeY', 'controlSizeZ', 'controlSize', 'controlSmoothing', 'controlOffsetX', 'controlOffsetY', 'controlOffsetZ', 'controlOffset' ]

                for node in nodes:
                    node_long = self.find_node( charRoot, node )
                    attrDict = { }
                    for attr in attrs:
                        if mc.attributeQuery( attr, node = node_long, exists = True ):

                            value = mc.getAttr( node_long + '.' + attr )
                            dv = mc.attributeQuery( attr, node = node_long, ld = True )[ 0 ]

                            if value != dv:
                                attrDict[ attr ] = value

                    if len( attrDict ) > 0:
                        ctrlDict[ node ] = attrDict

                if len( ctrlDict ) > 0:
                    data[ 'ControlShapeData' ] = ctrlDict

                # save meta data on root node
                self.set_metaData( charRoot, data )

                # Reset all Handles
                self.get_handles( character = charRoot, mode = 'reset', side = kAll )

                jointGrp = self.find_node( charRoot, 'Joint_Grp' )

                for jnt in mc.listRelatives( jointGrp, ad = True, c = True, typ = 'joint', pa=True ):
                    nodes = mc.listConnections( jnt + '.t', s = True, d = False ) or None
                    if nodes is not None:
                        if mc.nodeType( nodes[ 0 ] ) == 'multiplyDivide':
                            mc.delete( nodes[ 0 ] )

                # Store joint positions
                jointDict = self.get_joint_transform( charRoot )

                # Delete redundant nodes that will otherwise not be deleted, ie pairBlends, matrixInverse etc.
                if mc.attributeQuery( 'aux_nodes', node = charRoot, exists = True ):
                    con = mc.listConnections( charRoot + '.aux_nodes' ) or [ ]
                    if len( con ):
                        mc.delete( con )

                # Store Custom Controls
                customCtrls = self.get_char_handles( charRoot, { 'Type': kHandle, 'Side': kAll, 'Custom': True } )

                for customCtrl in customCtrls:
                    con = mc.listConnections( customCtrl + '.t', d = True ) or [ ]

                    if len( con ):
                        if mc.nodeType( con[ 0 ] ) == 'parentConstraint':
                            con = mc.listConnections( con[ 0 ] + '.constraintTranslateX' ) or [ ]

                            if len( con ):
                                self.rigCustomCtrls[ customCtrl ] = { 'Constraint': con[ 0 ] }

                # Delete the constraints on the upVec transforms or Maya will delete them when the corresponding
                # controls get deleted
                if type == kBipedRoot:
                    upVecs = [ 'Shoulder_Lft_upVec', 'Shoulder_Rgt_upVec', 'Hips_Lft_upVec', 'Hips_Rgt_upVec' ]

                    for up in upVecs:
                        up = self.find_node(charRoot, up)
                        try:
                            mc.delete( mc.listRelatives( up, c = 1, ad = 1, pa=True ) )
                        except:
                            pass

                controls = mc.listRelatives( rig_grp, c = True, pa = True )

                if controls is not None:
                    try:
                        mc.delete( controls )
                    except:
                        pass

                # Restore joint positions
                self.set_joint_transform( charRoot, jointDict )

    def delete_mocap( self, *args ):

        if args:
            charRoot = args[0]

        charRoot = self.get_active_char()
        mocap_grp = self.find_node(charRoot, 'Mocap_Grp')
        if mocap_grp is not None:
            nodes = mc.listRelatives( mocap_grp, c=True, pa=True)
            if nodes is not None:

                # Delete HIK Definition and state nodes
                con = mc.listConnections( nodes[0] + '.Character' ) or []
                if len( con ) > 0:
                    if mc.nodeType( con[0] ) == 'HIKCharacterNode':
                        con2 = mc.listConnections( con[0] + '.propertyState') or []
                        if len( con2 ) > 0:
                            mc.delete( con2[0] )
                        mc.delete( con[0] )

                try:
                    mc.delete( nodes )
                except:
                    pass

    def get_aux_joints(self, type ):
        if type == kBiped:
          return  {
             "Skeleton": {
              "Joints": {
               "Middle3_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle2_Lft_Jnt",
                "tx": 3.1684
               },
               "Shoulder_Blend_Lft_Jnt": {
                "parent": "Clavicle_Lft_Jnt",
                "nodeType": "joint",
                "radius": 2.0,
                "rz": -20.0,
                "tx": 10.5751
               },
               "LegUp_Aux2_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Lft_Jnt",
                "ty": -19.5
               },
               "Pinky2_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky1_Lft_Jnt",
                "tx": 4.7646
               },
               "Ring2_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring1_Lft_Jnt",
                "tx": 5.2284
               },
               "Ball_Rgt_Jnt_Blend": {
                "radius": 2.0,
                "tz": -11.97,
                "nodeType": "joint",
                "parent": "Foot_Rgt_Jnt",
                "ty": 6.335
               },
               "ArmUp_Aux2_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Lft_Jnt",
                "tx": 11.5
               },
               "Middle4_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle3_Lft_Jnt",
                "tx": 2.7589
               },
               "LegLo_Lft_Jnt_Blend": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "LegUp_Lft_Jnt",
                "ty": -39.0
               },
               "Index2_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index1_Lft_Jnt",
                "tx": 5.7251
               },
               "LegLo_Aux2_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Rgt_Jnt",
                "ty": 20.5
               },
               "Thumb1_Blend_Lft_Jnt": {
                "tz": 2.3289,
                "parent": "Palm_Lft_Jnt",
                "tx": -0.4241,
                "ty": -1.0611,
                "jox": 119.0176,
                "joy": -29.5243,
                "joz": -36.8969,
                "radius": 2.0,
                "nodeType": "joint"
               },
               "Index2_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index1_Rgt_Jnt",
                "tx": -5.7251
               },
               "Pinky4_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky3_Rgt_Jnt",
                "tx": -2.2206
               },
               "Middle2_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle1_Rgt_Jnt",
                "tx": -5.6311
               },
               "Foot_Lft_Jnt_Blend": {
                "radius": 2.0,
                "rx": -1.9255,
                "nodeType": "joint",
                "parent": "LegLo_Lft_Jnt",
                "ty": -41.0
               },
               "Ring2_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring1_Rgt_Jnt",
                "tx": -5.2284
               },
               "LegLo_Aux3_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Rgt_Jnt",
                "ty": 30.75
               },
               "Shoulder_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "tx": -10.575,
                "parent": "Clavicle_Rgt_Jnt",
                "ty": -0.0005,
                "rz": -20.0,
                "radius": 2.0
               },
               "Pinky3_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky2_Lft_Jnt",
                "tx": 2.6751
               },
               "ArmLo_Aux1_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Lft_Jnt",
                "tx": 5.4
               },
               "LegUp_Aux1_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Lft_Jnt",
                "ty": -9.75
               },
               "ArmUp_Aux3_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Lft_Jnt",
                "tx": 17.25
               },
               "LegLo_Aux1_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Rgt_Jnt",
                "ty": 10.25
               },
               "Middle2_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle1_Lft_Jnt",
                "tx": 5.6311
               },
               "ArmUp_Aux3_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Rgt_Jnt",
                "tx": -17.25
               },
               "LegUp_Aux3_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Lft_Jnt",
                "ty": -29.25
               },
               "Middle3_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle2_Rgt_Jnt",
                "tx": -3.1684
               },
               "Thumb1_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "tx": 0.4241,
                "parent": "Palm_Rgt_Jnt",
                "ty": 1.0611,
                "radius": 2.0,
                "tz": -2.3289
               },
               "Thumb3_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Thumb2_Lft_Jnt",
                "tx": 3.7769
               },
               "Index4_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index3_Rgt_Jnt",
                "tx": -2.2613
               },
               "Wrist_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "ArmLo_Lft_Jnt",
                "tx": 21.6
               },
               "Index4_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index3_Lft_Jnt",
                "tx": 2.2613
               },
               "Pinky3_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky2_Rgt_Jnt",
                "tx": -2.6751
               },
               "ArmUp_Aux1_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Rgt_Jnt",
                "tx": -5.75
               },
               "Ring3_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring2_Lft_Jnt",
                "tx": 2.7781
               },
               "Ring3_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring2_Rgt_Jnt",
                "tx": -2.7781
               },
               "LegUp_Aux3_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Rgt_Jnt",
                "ty": 29.25
               },
               "ArmLo_Aux1_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Rgt_Jnt",
                "tx": -5.4
               },
               "Pinky4_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky3_Lft_Jnt",
                "tx": 2.2206
               },
               "LegLo_Aux1_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Lft_Jnt",
                "ty": -10.25
               },
               "Middle4_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Middle3_Rgt_Jnt",
                "tx": -2.7589
               },
               "LegUp_Rgt_Jnt_Blend": {
                "tz": -0.0597,
                "tx": -6.7,
                "parent": "Hips_Jnt",
                "ty": -5.9865,
                "rx": -178.0243,
                "radius": 2.0,
                "nodeType": "joint"
               },
               "Wrist_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "ArmLo_Rgt_Jnt",
                "tx": -21.6
               },
               "Thumb2_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Thumb1_Lft_Jnt",
                "tx": 3.6395
               },
               "Foot_Rgt_Jnt_Blend": {
                "radius": 2.0,
                "rx": -1.9255,
                "nodeType": "joint",
                "parent": "LegLo_Rgt_Jnt",
                "ty": 41.0
               },
               "Ring4_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring3_Lft_Jnt",
                "tx": 2.6052
               },
               "LegUp_Lft_Jnt_Blend": {
                "tz": -0.0597,
                "tx": 6.7,
                "parent": "Hips_Jnt",
                "ty": -5.9865,
                "rx": 1.9757,
                "radius": 2.0,
                "nodeType": "joint"
               },
               "ArmLo_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "ArmUp_Rgt_Jnt",
                "tx": -23.0
               },
               "ArmLo_Aux3_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Rgt_Jnt",
                "tx": -16.2
               },
               "ArmLo_Aux3_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Lft_Jnt",
                "tx": 16.2
               },
               "LegUp_Aux2_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Rgt_Jnt",
                "ty": 19.5
               },
               "ArmLo_Aux2_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Lft_Jnt",
                "tx": 10.8
               },
               "LegLo_Rgt_Jnt_Blend": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "LegUp_Rgt_Jnt",
                "ty": 39.0
               },
               "Thumb2_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Thumb1_Rgt_Jnt",
                "tx": -3.6395
               },
               "Ring4_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Ring3_Rgt_Jnt",
                "tx": -2.6052
               },
               "LegLo_Aux2_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Lft_Jnt",
                "ty": -20.5
               },
               "Index3_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index2_Lft_Jnt",
                "tx": 3.1627
               },
               "Index3_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Index2_Rgt_Jnt",
                "tx": -3.1627
               },
               "Thumb3_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Thumb2_Rgt_Jnt",
                "tx": -3.7769
               },
               "ArmUp_Aux1_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Lft_Jnt",
                "tx": 5.75
               },
               "Pinky2_Blend_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Pinky1_Rgt_Jnt",
                "tx": -4.7646
               },
               "ArmLo_Blend_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "ArmUp_Lft_Jnt",
                "tx": 23.0
               },
               "Ball_Lft_Jnt_Blend": {
                "radius": 2.0,
                "tz": 11.9696,
                "nodeType": "joint",
                "parent": "Foot_Lft_Jnt",
                "ty": -6.3351
               },
               "LegLo_Aux3_Lft_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegLo_Lft_Jnt",
                "ty": -30.75
               },
               "ArmLo_Aux2_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmLo_Rgt_Jnt",
                "tx": -10.8
               },
               "ArmUp_Aux2_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "ArmUp_Rgt_Jnt",
                "tx": -11.5
               },
               "LegUp_Aux1_Rgt_Jnt": {
                "nodeType": "joint",
                "radius": 3.0,
                "parent": "LegUp_Rgt_Jnt",
                "ty": 9.75
               },
               "Head_Jnt_Blend": {
                "nodeType": "joint",
                "radius": 2.0,
                "parent": "Neck_Jnt",
                "ty": 15.1352
               }
              }
             }
            }
        if type == kQuadrupedRoot:
          return  None

    def get_joints( self, type ):

        if type == kBiped:
            return {
                "Skeleton": {
                    "Joints": {
                        "Index1_Rgt_Jnt": {
                            "tz": -2.0798,
                            "parent": "Palm_Rgt_Jnt",
                            "tx": -1.659,
                            "ty": -0.7544,
                            "jox": 3.3828,
                            "joy": -8.0771,
                            "joz": 0.0538,
                            "nodeType": "joint"
                        },
                        "Pinky4_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky3_Rgt_Jnt",
                            "tx": -2.2206
                        },
                        "Ring1_Lft_Jnt": {
                            "tz": -0.3787,
                            "parent": "Palm_Lft_Jnt",
                            "tx": 1.7042,
                            "ty": 0.899,
                            "jox": 3.4171,
                            "joy": 7.7111,
                            "joz": 0.6353,
                            "nodeType": "joint"
                        },
                        "Jaw_Jnt_Tip": {
                            "radius": 5.0,
                            "tz": 8.6143,
                            "nodeType": "joint",
                            "parent": "Jaw_Jnt"
                        },
                        "Eye_Lft_Jnt": {
                            "nodeType": "joint",
                            "tx": 3.2461,
                            "parent": "Head_Jnt",
                            "ty": 3.604,
                            "radius": 5.0,
                            "tz": 6.4812
                        },
                        "Chest_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Spine3_Jnt",
                            "ty": 4.7069
                        },
                        "Toes_Rgt_Jnt": {
                            "radius": 5.0,
                            "tz": -11.97,
                            "nodeType": "joint",
                            "parent": "Foot_Rgt_Jnt",
                            "ty": 6.335
                        },
                        "Index4_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index3_Rgt_Jnt",
                            "tx": -2.2613
                        },
                        "Root_Jnt": {
                            "nodeType": "joint",
                            "parent": "Joint_Grp"
                        },
                        "ArmUp_Lft_Jnt": {
                            "parent": "Clavicle_Lft_Jnt",
                            "nodeType": "joint",
                            "radius": 5.0,
                            "rz": -40.0,
                            "tx": 10.5751
                        },
                        "Pinky3_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky2_Rgt_Jnt",
                            "tx": -2.6751
                        },
                        "Hand_Rgt_upVec": {
                            "nodeType": "transform",
                            "tz": -5.0,
                            "parent": "Hand_Rgt_Jnt"
                        },
                        "Shoulder_Blend_Rgt_Loc": {
                            "nodeType": "transform",
                            "parent": "Clavicle_Rgt_Jnt",
                            "rz": -40.0
                        },
                        "Index3_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index2_Lft_Jnt",
                            "tx": 3.1627
                        },
                        "Hips_Lft_upVec": {
                            "nodeType": "transform",
                            "tx": 16.7,
                            "parent": "Hips_Jnt",
                            "ty": -5.9865,
                            "rx": 3.9515,
                            "tz": -0.0597
                        },
                        "Middle2_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle1_Lft_Jnt",
                            "tx": 5.6311
                        },
                        "Hand_Lft_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "ArmLo_Lft_Jnt",
                            "tx": 21.6
                        },
                        "Clavicle_Rgt_Jnt": {
                            "tz": -2.3918,
                            "tx": -1.7794,
                            "parent": "Chest_Jnt",
                            "ty": 17.0561,
                            "rx": 180.0,
                            "radius": 5.0,
                            "nodeType": "joint"
                        },
                        "Middle2_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle1_Rgt_Jnt",
                            "tx": -5.6311
                        },
                        "Clavicle_Lft_Jnt": {
                            "nodeType": "joint",
                            "tx": 1.7794,
                            "parent": "Chest_Jnt",
                            "ty": 17.0561,
                            "radius": 5.0,
                            "tz": -2.3918
                        },
                        "Eye_Rgt_Jnt": {
                            "nodeType": "joint",
                            "tx": -3.246,
                            "parent": "Head_Jnt",
                            "ty": 3.604,
                            "radius": 5.0,
                            "tz": 6.4812
                        },
                        "Heel_Lft_Jnt": {
                            "radius": 5.0,
                            "tz": -4.5,
                            "nodeType": "joint",
                            "parent": "Foot_Lft_Jnt",
                            "ty": -7.7
                        },
                        "Shoulder_Blend_Lft_Loc": {
                            "nodeType": "transform",
                            "parent": "Clavicle_Lft_Jnt",
                            "rz": -40.0
                        },
                        "Ring3_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring2_Rgt_Jnt",
                            "tx": -2.7781
                        },
                        "Thumb1_Lft_Jnt": {
                            "tz": 2.3289,
                            "parent": "Palm_Lft_Jnt",
                            "tx": -0.4241,
                            "ty": -1.0611,
                            "jox": 119.0176,
                            "joy": -29.5243,
                            "joz": -36.8969,
                            "nodeType": "joint"
                        },
                        "Foot_Rgt_Jnt": {
                            "radius": 5.0,
                            "rx": -3.8509,
                            "nodeType": "joint",
                            "parent": "LegLo_Rgt_Jnt",
                            "ty": 41.0
                        },
                        "Heel_Rgt_Jnt": {
                            "radius": 5.0,
                            "tz": 4.5,
                            "nodeType": "joint",
                            "parent": "Foot_Rgt_Jnt",
                            "ty": 7.7
                        },
                        "Thumb2_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Thumb1_Lft_Jnt",
                            "tx": 3.6395
                        },
                        "Palm_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Hand_Rgt_Jnt",
                            "tx": -1.9237,
                            "ty": 0.0003
                        },
                        "Hips_Rgt_upVec": {
                            "nodeType": "transform",
                            "tx": -16.7,
                            "parent": "Hips_Jnt",
                            "ty": -5.9865,
                            "rx": 3.9515,
                            "tz": -0.0597
                        },
                        "Index2_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index1_Lft_Jnt",
                            "tx": 5.7251
                        },
                        "LegLo_Rgt_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "LegUp_Rgt_Jnt",
                            "ty": 39.0
                        },
                        "ToesTip_Rgt_Jnt": {
                            "radius": 5.0,
                            "tz": -5.6,
                            "nodeType": "joint",
                            "parent": "Toes_Rgt_Jnt",
                            "ty": 1.4
                        },
                        "Thumb1_Rgt_Jnt": {
                            "tz": -2.3289,
                            "parent": "Palm_Rgt_Jnt",
                            "tx": 0.4241,
                            "ty": 1.0611,
                            "jox": 119.0176,
                            "joy": -29.5243,
                            "joz": -36.8969,
                            "nodeType": "joint"
                        },
                        "Pinky4_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky3_Lft_Jnt",
                            "tx": 2.2206
                        },
                        "ArmLo_Rgt_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "ArmUp_Rgt_Jnt",
                            "tx": -23.0
                        },
                        "Hand_Lft_upVec": {
                            "nodeType": "transform",
                            "tz": 5.0,
                            "parent": "Hand_Lft_Jnt"
                        },
                        "Shoulder_Lft_upVec": {
                            "nodeType": "transform",
                            "parent": "Clavicle_Lft_Jnt",
                            "tx": 14.1363,
                            "ty": 9.3456
                        },
                        "ArmUp_Rgt_Jnt": {
                            "nodeType": "joint",
                            "tx": -10.575,
                            "parent": "Clavicle_Rgt_Jnt",
                            "ty": -0.0005,
                            "rz": -40.0,
                            "radius": 5.0
                        },
                        "Middle4_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle3_Lft_Jnt",
                            "tx": 2.7589
                        },
                        "Ankle_Rgt_upVec": {
                            "nodeType": "transform",
                            "parent": "Foot_Rgt_Jnt",
                            "tx": -10.0
                        },
                        "Ring2_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring1_Lft_Jnt",
                            "tx": 5.2284
                        },
                        "Ring1_Rgt_Jnt": {
                            "tz": 0.3787,
                            "parent": "Palm_Rgt_Jnt",
                            "tx": -1.7042,
                            "ty": -0.899,
                            "jox": 3.4171,
                            "joy": 7.7111,
                            "joz": 0.6353,
                            "nodeType": "joint"
                        },
                        "Ankle_Lft_upVec": {
                            "nodeType": "transform",
                            "parent": "Foot_Lft_Jnt",
                            "tx": 10.0
                        },
                        "Ring2_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring1_Rgt_Jnt",
                            "tx": -5.2284
                        },
                        "Index2_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index1_Rgt_Jnt",
                            "tx": -5.7251
                        },
                        "Pinky2_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky1_Lft_Jnt",
                            "tx": 4.7646
                        },
                        "Shoulder_Rgt_upVec": {
                            "nodeType": "transform",
                            "parent": "Clavicle_Rgt_Jnt",
                            "tx": -12.5857,
                            "ty": -9.9104
                        },
                        "Ring4_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring3_Lft_Jnt",
                            "tx": 2.6052
                        },
                        "Index1_Lft_Jnt": {
                            "tz": 2.0798,
                            "parent": "Palm_Lft_Jnt",
                            "tx": 1.659,
                            "ty": 0.7544,
                            "jox": 3.3828,
                            "joy": -8.0771,
                            "joz": 0.0538,
                            "nodeType": "joint"
                        },
                        "ArmLo_Lft_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "ArmUp_Lft_Jnt",
                            "tx": 23.0
                        },
                        "Ring4_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring3_Rgt_Jnt",
                            "tx": -2.6052
                        },
                        "Middle4_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle3_Rgt_Jnt",
                            "tx": -2.7589
                        },
                        "Hips_Blend_Lft_Loc": {
                            "nodeType": "transform",
                            "rx": 3.9514,
                            "parent": "Hips_Jnt",
                            "tx": 5.0
                        },
                        "LegLo_Lft_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "LegUp_Lft_Jnt",
                            "ty": -39.0
                        },
                        "Middle3_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle2_Rgt_Jnt",
                            "tx": -3.1684
                        },
                        "Spine3_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Spine2_Jnt",
                            "ty": 4.2884
                        },
                        "Hips_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Root_Jnt",
                            "ty": 93.9799
                        },
                        "Foot_Lft_Jnt": {
                            "radius": 5.0,
                            "rx": -3.851,
                            "nodeType": "joint",
                            "parent": "LegLo_Lft_Jnt",
                            "ty": -41.0
                        },
                        "Hand_Rgt_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "ArmLo_Rgt_Jnt",
                            "tx": -21.6
                        },
                        "Pinky1_Lft_Jnt": {
                            "tz": -1.6195,
                            "parent": "Palm_Lft_Jnt",
                            "tx": 1.5354,
                            "ty": 0.9719,
                            "jox": -8.0,
                            "joy": 11.7109,
                            "joz": 0.6429,
                            "rx": -0.0254,
                            "ry": 1.481,
                            "rz": -0.9841,
                            "nodeType": "joint"
                        },
                        "Spine1_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Hips_Jnt",
                            "ty": 1.7192
                        },
                        "Neck_Jnt": {
                            "tz": -2.7845,
                            "parent": "Chest_Jnt",
                            "ty": 19.8097,
                            "jox": 10.0,
                            "radius": 5.0,
                            "nodeType": "joint"
                        },
                        "Thumb3_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Thumb2_Rgt_Jnt",
                            "tx": -3.7769
                        },
                        "Head_Jnt": {
                            "jox": -10.0,
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Neck_Jnt",
                            "ty": 15.1352
                        },
                        "Pinky3_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky2_Lft_Jnt",
                            "tx": 2.6751
                        },
                        "Pinky1_Rgt_Jnt": {
                            "tz": 1.6195,
                            "parent": "Palm_Rgt_Jnt",
                            "tx": -1.5354,
                            "ty": -0.9719,
                            "jox": 3.4624,
                            "joy": 11.7109,
                            "joz": 0.6429,
                            "rx": -11.4889,
                            "ry": 1.2559,
                            "rz": -1.2588,
                            "nodeType": "joint"
                        },
                        "Middle1_Rgt_Jnt": {
                            "tz": -1.2301,
                            "parent": "Palm_Rgt_Jnt",
                            "tx": -1.7795,
                            "ty": -0.8052,
                            "jox": 3.3507,
                            "joy": 1.7115,
                            "joz": 0.6298,
                            "nodeType": "joint"
                        },
                        "Palm_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Hand_Lft_Jnt",
                            "tx": 1.9233
                        },
                        "Prop_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Palm_Lft_Jnt",
                            "tx": 5,
                            "ty": -2
                        },
                        "Prop_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Palm_Rgt_Jnt",
                            "tx": -5,
                            "ty": 2
                        },
                        "Index3_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index2_Rgt_Jnt",
                            "tx": -3.1627
                        },
                        "Toes_Lft_Jnt": {
                            "radius": 5.0,
                            "tz": 11.9696,
                            "nodeType": "joint",
                            "parent": "Foot_Lft_Jnt",
                            "ty": -6.3351
                        },
                        "Ring3_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Ring2_Lft_Jnt",
                            "tx": 2.7781
                        },
                        "Jaw_Jnt": {
                            "tz": 2.0289,
                            "parent": "Head_Jnt",
                            "ty": -1.172,
                            "jox": 16.2,
                            "radius": 5.0,
                            "nodeType": "joint"
                        },
                        "Middle3_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Middle2_Lft_Jnt",
                            "tx": 3.1684
                        },
                        "Spine2_Jnt": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Spine1_Jnt",
                            "ty": 3.5746
                        },
                        "ToesTip_Lft_Jnt": {
                            "radius": 5.0,
                            "tz": 5.6,
                            "nodeType": "joint",
                            "parent": "Toes_Lft_Jnt",
                            "ty": -1.4
                        },
                        "Hips_Blend_Rgt_Loc": {
                            "nodeType": "transform",
                            "rx": -176.0486,
                            "parent": "Hips_Jnt",
                            "tx": -5.0
                        },
                        "LegUp_Rgt_Jnt": {
                            "tz": -0.0597,
                            "tx": -6.7,
                            "parent": "Hips_Jnt",
                            "ty": -5.9865,
                            "rx": -176.0486,
                            "radius": 5.0,
                            "nodeType": "joint"
                        },
                        "LegUp_Lft_Jnt": {
                            "tz": -0.0597,
                            "tx": 6.7,
                            "parent": "Hips_Jnt",
                            "ty": -5.9865,
                            "rx": 3.9514,
                            "radius": 5.0,
                            "nodeType": "joint"
                        },
                        "Thumb2_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Thumb1_Rgt_Jnt",
                            "tx": -3.6395
                        },
                        "Head_Jnt_Tip": {
                            "nodeType": "joint",
                            "radius": 5.0,
                            "parent": "Head_Jnt",
                            "ty": 10.7265
                        },
                        "Middle1_Lft_Jnt": {
                            "tz": 1.2301,
                            "parent": "Palm_Lft_Jnt",
                            "tx": 1.7795,
                            "ty": 0.8052,
                            "jox": 3.3507,
                            "joy": 1.7115,
                            "joz": 0.6298,
                            "nodeType": "joint"
                        },
                        "Index4_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Index3_Lft_Jnt",
                            "tx": 2.2613
                        },
                        "Pinky2_Rgt_Jnt": {
                            "nodeType": "joint",
                            "parent": "Pinky1_Rgt_Jnt",
                            "tx": -4.7646
                        },
                        "Thumb3_Lft_Jnt": {
                            "nodeType": "joint",
                            "parent": "Thumb2_Lft_Jnt",
                            "tx": 3.7769
                        }
                    }
                }
            }

        if type == kBipedUE:
            return {
                "Skeleton": {
                    "Joints": {
                        "root": {
                            "jox": -90,
                            "radius": 3.0,
                            "parent": "Joint_Grp",
                            "nodeType": "joint"
                        },
                        "pelvis": {
                            "ty": -2.3795,
                            "tz": 98.6932,
                            "rx": -90.0,
                            "ry": -86.3974,
                            "rz": 90.0,
                            "radius": 3.0,
                            "parent": "root",
                            "nodeType": "joint"
                        },
                        "spine_01": {
                            "tx": 2.4719,
                            "rx": 0.0001,
                            "rz": -17.2467,
                            "radius": 3.0,
                            "parent": "pelvis",
                            "nodeType": "joint"
                        },
                        "spine_02": {
                            "tx": 4.9875,
                            "rx": -0.0002,
                            "rz": 6.825,
                            "radius": 3.0,
                            "parent": "spine_01",
                            "nodeType": "joint"
                        },
                        "spine_03": {
                            "tx": 7.6259,
                            "rx": 0.0002,
                            "rz": 10.3212,
                            "radius": 3.0,
                            "parent": "spine_02",
                            "nodeType": "joint"
                        },
                        "spine_04": {
                            "tx": 8.8511,
                            "rx": 0.0002,
                            "rz": 8.4786,
                            "radius": 3.0,
                            "parent": "spine_03",
                            "nodeType": "joint"
                        },
                        "spine_05": {
                            "tx": 17.4988,
                            "rx": -0.0002,
                            "rz": 0.2585,
                            "radius": 3.0,
                            "parent": "spine_04",
                            "nodeType": "joint"
                        },
                        "neck_01": {
                            "tx": 11.915,
                            "ry": -0.0001,
                            "rz": -25.1344,
                            "radius": 3.0,
                            "parent": "spine_05",
                            "nodeType": "joint"
                        },
                        "neck_02": {
                            "tx": 5.8488,
                            "rx": -0.0005,
                            "rz": 0.604,
                            "radius": 3.0,
                            "parent": "neck_01",
                            "nodeType": "joint"
                        },
                        "head": {
                            "tx": 5.7585,
                            "rx": 0.0003,
                            "ry": -0.0001,
                            "rz": 12.2912,
                            "radius": 3.0,
                            "parent": "neck_02",
                            "nodeType": "joint"
                        },
                        "clavicle_l": {
                            "tx": 5.8309,
                            "ty": 1.0048,
                            "tz": -0.9314,
                            "rx": 168.9537,
                            "ry": 81.6483,
                            "rz": 156.7854,
                            "radius": 3.0,
                            "parent": "spine_05",
                            "nodeType": "joint"
                        },
                        "upperarm_l": {
                            "tx": 15.2861,
                            "rx": -4.581,
                            "ry": 44.6755,
                            "rz": -3.614,
                            "radius": 3.0,
                            "parent": "clavicle_l",
                            "nodeType": "joint"
                        },
                        "lowerarm_l": {
                            "tx": 27.0904,
                            "rz": -36.7004,
                            "radius": 3.0,
                            "parent": "upperarm_l",
                            "nodeType": "joint"
                        },
                        "lowerarm_twist_02_l": {
                            "tx": 8.6984,
                            "rx": 0.1429,
                            "ry": -0.192,
                            "rz": 0.0669,
                            "radius": 3.0,
                            "parent": "lowerarm_l",
                            "nodeType": "joint"
                        },
                        "lowerarm_twist_01_l": {
                            "tx": 17.3968,
                            "rx": 0.1429,
                            "ry": -0.192,
                            "rz": 0.0669,
                            "radius": 3.0,
                            "parent": "lowerarm_l",
                            "nodeType": "joint"
                        },
                        "hand_l": {
                            "tx": 26.0952,
                            "rx": -72.649,
                            "ry": 10.4382,
                            "rz": 3.7481,
                            "radius": 3.0,
                            "parent": "lowerarm_l",
                            "nodeType": "joint"
                        },
                        "middle_metacarpal_l": {
                            "tx": 3.1166,
                            "ty": -0.0677,
                            "tz": -0.3645,
                            "rx": 0.1733,
                            "ry": -2.0096,
                            "rz": -7.1628,
                            "radius": 3.0,
                            "parent": "hand_l",
                            "nodeType": "joint"
                        },
                        "middle_01_l": {
                            "tx": 5.5605,
                            "rx": -3.6731,
                            "ry": -4.2859,
                            "rz": 24.0416,
                            "radius": 3.0,
                            "parent": "middle_metacarpal_l",
                            "nodeType": "joint"
                        },
                        "middle_02_l": {
                            "tx": 4.9197,
                            "rx": 0.0919,
                            "ry": 0.4761,
                            "rz": 19.1529,
                            "radius": 3.0,
                            "parent": "middle_01_l",
                            "nodeType": "joint"
                        },
                        "middle_03_l": {
                            "tx": 2.9021,
                            "rx": -0.0109,
                            "ry": -0.2186,
                            "rz": 2.8503,
                            "radius": 3.0,
                            "parent": "middle_02_l",
                            "nodeType": "joint"
                        },
                        "pinky_metacarpal_l": {
                            "tx": 2.9831,
                            "ty": 0.242,
                            "tz": 1.9275,
                            "rx": -25.3734,
                            "ry": -21.6206,
                            "rz": 9.1694,
                            "radius": 3.0,
                            "parent": "hand_l",
                            "nodeType": "joint"
                        },
                        "pinky_01_l": {
                            "tx": 4.7179,
                            "rx": 0.2654,
                            "ry": 1.1126,
                            "rz": 11.7384,
                            "radius": 3.0,
                            "parent": "pinky_metacarpal_l",
                            "nodeType": "joint"
                        },
                        "pinky_02_l": {
                            "tx": 2.8933,
                            "rx": -0.1015,
                            "ry": -0.1857,
                            "rz": 20.2972,
                            "radius": 3.0,
                            "parent": "pinky_01_l",
                            "nodeType": "joint"
                        },
                        "pinky_03_l": {
                            "tx": 1.7915,
                            "rx": -0.0053,
                            "ry": -0.0838,
                            "rz": 3.2541,
                            "radius": 3.0,
                            "parent": "pinky_02_l",
                            "nodeType": "joint"
                        },
                        "ring_metacarpal_l": {
                            "tx": 3.1086,
                            "ty": 0.0603,
                            "tz": 0.8014,
                            "rx": -10.1363,
                            "ry": -13.6762,
                            "rz": -2.8714,
                            "radius": 3.0,
                            "parent": "hand_l",
                            "nodeType": "joint"
                        },
                        "ring_01_l": {
                            "tx": 4.9928,
                            "rx": -0.6691,
                            "ry": 0.7738,
                            "rz": 17.9148,
                            "radius": 3.0,
                            "parent": "ring_metacarpal_l",
                            "nodeType": "joint"
                        },
                        "ring_02_l": {
                            "tx": 4.2514,
                            "rx": 0.0396,
                            "ry": 0.4462,
                            "rz": 26.3775,
                            "radius": 3.0,
                            "parent": "ring_01_l",
                            "nodeType": "joint"
                        },
                        "ring_03_l": {
                            "tx": 3.2348,
                            "rx": -0.0303,
                            "ry": -0.3676,
                            "rz": 4.6278,
                            "radius": 3.0,
                            "parent": "ring_02_l",
                            "nodeType": "joint"
                        },
                        "thumb_01_l": {
                            "tx": 2.31,
                            "ty": 1.4519,
                            "tz": -2.5471,
                            "rx": 81.9997,
                            "ry": 33.1928,
                            "rz": 20.2681,
                            "radius": 3.0,
                            "parent": "hand_l",
                            "nodeType": "joint"
                        },
                        "thumb_02_l": {
                            "tx": 4.6318,
                            "rx": -1.0676,
                            "ry": -6.2937,
                            "rz": 20.2302,
                            "radius": 3.0,
                            "parent": "thumb_01_l",
                            "nodeType": "joint"
                        },
                        "thumb_03_l": {
                            "tx": 2.7106,
                            "rx": 0.0305,
                            "ry": 0.195,
                            "rz": 8.4044,
                            "radius": 3.0,
                            "parent": "thumb_02_l",
                            "nodeType": "joint"
                        },
                        "index_metacarpal_l": {
                            "tx": 3.4527,
                            "ty": 0.1128,
                            "tz": -2.0519,
                            "rx": 17.5598,
                            "ry": 5.6408,
                            "rz": -3.8649,
                            "radius": 3.0,
                            "parent": "hand_l",
                            "nodeType": "joint"
                        },
                        "index_01_l": {
                            "tx": 5.3769,
                            "rx": -10.6019,
                            "ry": -4.4455,
                            "rz": 19.2285,
                            "radius": 3.0,
                            "parent": "index_metacarpal_l",
                            "nodeType": "joint"
                        },
                        "index_02_l": {
                            "tx": 4.5645,
                            "rx": 0.0651,
                            "ry": 0.2475,
                            "rz": 11.7142,
                            "radius": 3.0,
                            "parent": "index_01_l",
                            "nodeType": "joint"
                        },
                        "index_03_l": {
                            "tx": 2.4865,
                            "ry": 0.0602,
                            "rz": -0.0124,
                            "radius": 3.0,
                            "parent": "index_02_l",
                            "nodeType": "joint"
                        },
                        "upperarm_twist_01_l": {
                            "tx": 9.0301,
                            "ry": -0.2393,
                            "rz": 0.0137,
                            "radius": 3.0,
                            "parent": "upperarm_l",
                            "nodeType": "joint"
                        },
                        "upperarm_twist_02_l": {
                            "tx": 18.0602,
                            "radius": 3.0,
                            "parent": "upperarm_l",
                            "nodeType": "joint"
                        },
                        "clavicle_r": {
                            "tx": 5.8304,
                            "ty": 1.0049,
                            "tz": 0.9314,
                            "rx": 168.9521,
                            "ry": 81.6482,
                            "rz": -23.2162,
                            "radius": 3.0,
                            "parent": "spine_05",
                            "nodeType": "joint"
                        },
                        "upperarm_r": {
                            "tx": -15.286,
                            "tz": -0.0004,
                            "rx": -4.581,
                            "ry": 44.6755,
                            "rz": -3.614,
                            "radius": 3.0,
                            "parent": "clavicle_r",
                            "nodeType": "joint"
                        },
                        "lowerarm_r": {
                            "tx": -27.0899,
                            "rz": -36.7004,
                            "radius": 3.0,
                            "parent": "upperarm_r",
                            "nodeType": "joint"
                        },
                        "lowerarm_twist_02_r": {
                            "tx": -8.6985,
                            "rx": 0.1429,
                            "ry": -0.192,
                            "rz": 0.0669,
                            "radius": 3.0,
                            "parent": "lowerarm_r",
                            "nodeType": "joint"
                        },
                        "lowerarm_twist_01_r": {
                            "tx": -17.397,
                            "rx": 0.1429,
                            "ry": -0.192,
                            "rz": 0.0669,
                            "radius": 3.0,
                            "parent": "lowerarm_r",
                            "nodeType": "joint"
                        },
                        "hand_r": {
                            "tx": -26.0955,
                            "rx": -72.649,
                            "ry": 10.4382,
                            "rz": 3.7481,
                            "radius": 3.0,
                            "parent": "lowerarm_r",
                            "nodeType": "joint"
                        },
                        "middle_metacarpal_r": {
                            "tx": -3.1166,
                            "ty": 0.0677,
                            "tz": 0.3642,
                            "rx": 0.1733,
                            "ry": -2.0096,
                            "rz": -7.1628,
                            "radius": 3.0,
                            "parent": "hand_r",
                            "nodeType": "joint"
                        },
                        "middle_01_r": {
                            "tx": -5.5606,
                            "rx": -3.6731,
                            "ry": -4.2859,
                            "rz": 24.0416,
                            "radius": 3.0,
                            "parent": "middle_metacarpal_r",
                            "nodeType": "joint"
                        },
                        "middle_02_r": {
                            "tx": -4.9196,
                            "rx": 0.0919,
                            "ry": 0.4761,
                            "rz": 19.1529,
                            "radius": 3.0,
                            "parent": "middle_01_r",
                            "nodeType": "joint"
                        },
                        "middle_03_r": {
                            "tx": -2.9021,
                            "rx": -0.0109,
                            "ry": -0.2186,
                            "rz": 2.8503,
                            "radius": 3.0,
                            "parent": "middle_02_r",
                            "nodeType": "joint"
                        },
                        "pinky_metacarpal_r": {
                            "tx": -2.9831,
                            "ty": -0.242,
                            "tz": -1.9278,
                            "rx": -25.3734,
                            "ry": -21.6206,
                            "rz": 9.1694,
                            "radius": 3.0,
                            "parent": "hand_r",
                            "nodeType": "joint"
                        },
                        "pinky_01_r": {
                            "tx": -4.718,
                            "rx": 0.2654,
                            "ry": 1.1126,
                            "rz": 11.7384,
                            "radius": 3.0,
                            "parent": "pinky_metacarpal_r",
                            "nodeType": "joint"
                        },
                        "pinky_02_r": {
                            "tx": -2.8933,
                            "tz": 0.0001,
                            "rx": -0.1015,
                            "ry": -0.1857,
                            "rz": 20.2972,
                            "radius": 3.0,
                            "parent": "pinky_01_r",
                            "nodeType": "joint"
                        },
                        "pinky_03_r": {
                            "tx": -1.7915,
                            "rx": -0.0053,
                            "ry": -0.0838,
                            "rz": 3.2541,
                            "radius": 3.0,
                            "parent": "pinky_02_r",
                            "nodeType": "joint"
                        },
                        "ring_metacarpal_r": {
                            "tx": -3.1086,
                            "ty": -0.0604,
                            "tz": -0.8016,
                            "rx": -10.1363,
                            "ry": -13.6762,
                            "rz": -2.8714,
                            "radius": 3.0,
                            "parent": "hand_r",
                            "nodeType": "joint"
                        },
                        "ring_01_r": {
                            "tx": -4.9928,
                            "ty": 0.0001,
                            "rx": -0.6691,
                            "ry": 0.7738,
                            "rz": 17.9148,
                            "radius": 3.0,
                            "parent": "ring_metacarpal_r",
                            "nodeType": "joint"
                        },
                        "ring_02_r": {
                            "tx": -4.2514,
                            "ty": -0.0001,
                            "rx": 0.0396,
                            "ry": 0.4462,
                            "rz": 26.3775,
                            "radius": 3.0,
                            "parent": "ring_01_r",
                            "nodeType": "joint"
                        },
                        "ring_03_r": {
                            "tx": -3.2347,
                            "ty": 0.0001,
                            "rx": -0.0303,
                            "ry": -0.3676,
                            "rz": 4.6278,
                            "radius": 3.0,
                            "parent": "ring_02_r",
                            "nodeType": "joint"
                        },
                        "thumb_01_r": {
                            "tx": -2.3101,
                            "ty": -1.4519,
                            "tz": 2.5468,
                            "rx": 81.9997,
                            "ry": 33.1928,
                            "rz": 20.2681,
                            "radius": 3.0,
                            "parent": "hand_r",
                            "nodeType": "joint"
                        },
                        "thumb_02_r": {
                            "tx": -4.6318,
                            "rx": -1.0676,
                            "ry": -6.2937,
                            "rz": 20.2302,
                            "radius": 3.0,
                            "parent": "thumb_01_r",
                            "nodeType": "joint"
                        },
                        "thumb_03_r": {
                            "tx": -2.7106,
                            "ty": -0.0001,
                            "rx": 0.0305,
                            "ry": 0.195,
                            "rz": 8.4044,
                            "radius": 3.0,
                            "parent": "thumb_02_r",
                            "nodeType": "joint"
                        },
                        "index_metacarpal_r": {
                            "tx": -3.4527,
                            "ty": -0.1128,
                            "tz": 2.0516,
                            "rx": 17.5598,
                            "ry": 5.6408,
                            "rz": -3.8649,
                            "radius": 3.0,
                            "parent": "hand_r",
                            "nodeType": "joint"
                        },
                        "index_01_r": {
                            "tx": -5.3769,
                            "rx": -10.6019,
                            "ry": -4.4455,
                            "rz": 19.2285,
                            "radius": 3.0,
                            "parent": "index_metacarpal_r",
                            "nodeType": "joint"
                        },
                        "index_02_r": {
                            "tx": -4.5646,
                            "ty": 0.0001,
                            "rx": 0.0651,
                            "ry": 0.2475,
                            "rz": 11.7142,
                            "radius": 3.0,
                            "parent": "index_01_r",
                            "nodeType": "joint"
                        },
                        "index_03_r": {
                            "tx": -2.4864,
                            "ry": 0.0602,
                            "rz": -0.0124,
                            "radius": 3.0,
                            "parent": "index_02_r",
                            "nodeType": "joint"
                        },
                        "upperarm_twist_01_r": {
                            "tx": -9.03,
                            "tz": -0.0001,
                            "ry": -0.2393,
                            "rz": 0.0137,
                            "radius": 3.0,
                            "parent": "upperarm_r",
                            "nodeType": "joint"
                        },
                        "upperarm_twist_02_r": {
                            "tx": -18.0599,
                            "tz": -0.0003,
                            "radius": 3.0,
                            "parent": "upperarm_r",
                            "nodeType": "joint"
                        },
                        "thigh_r": {
                            "tx": -3.232,
                            "ty": -0.068,
                            "tz": 11.1546,
                            "rx": 8.4755,
                            "ry": -2.3902,
                            "rz": 175.2025,
                            "radius": 3.0,
                            "parent": "pelvis",
                            "nodeType": "joint"
                        },
                        "calf_r": {
                            "tx": 45.7519,
                            "rz": -1.0935,
                            "radius": 3.0,
                            "parent": "thigh_r",
                            "nodeType": "joint"
                        },
                        "foot_r": {
                            "tx": 41.7055,
                            "rx": 0.0051,
                            "ry": 2.5398,
                            "rz": 0.1138,
                            "radius": 3.0,
                            "parent": "calf_r",
                            "nodeType": "joint"
                        },
                        "ball_r": {
                            "tx": 6.5368,
                            "ty": 13.6292,
                            "tz": -0.0439,
                            "rz": -90.0,
                            "radius": 3.0,
                            "parent": "foot_r",
                            "nodeType": "joint"
                        },
                        "calf_twist_02_r": {
                            "tx": 13.9018,
                            "tz": 0.05,
                            "rx": 0.005,
                            "ry": -0.2832,
                            "rz": 0.1135,
                            "radius": 3.0,
                            "parent": "calf_r",
                            "nodeType": "joint"
                        },
                        "calf_twist_01_r": {
                            "tx": 27.8036,
                            "tz": 0.1,
                            "rx": 0.005,
                            "ry": -0.2832,
                            "rz": 0.1135,
                            "radius": 3.0,
                            "parent": "calf_r",
                            "nodeType": "joint"
                        },
                        "thigh_twist_01_r": {
                            "tx": 15.2506,
                            "rx": -0.0001,
                            "ry": -0.2833,
                            "rz": 0.0533,
                            "radius": 3.0,
                            "parent": "thigh_r",
                            "nodeType": "joint"
                        },
                        "thigh_twist_02_r": {
                            "tx": 30.5013,
                            "rx": -0.0001,
                            "ry": -0.2833,
                            "rz": 0.0533,
                            "radius": 3.0,
                            "parent": "thigh_r",
                            "nodeType": "joint"
                        },
                        "thigh_l": {
                            "tx": -3.232,
                            "ty": -0.068,
                            "tz": -11.1546,
                            "rx": 8.4755,
                            "ry": -2.3902,
                            "rz": -4.7975,
                            "radius": 3.0,
                            "parent": "pelvis",
                            "nodeType": "joint"
                        },
                        "calf_l": {
                            "tx": -45.752,
                            "rz": -1.0935,
                            "radius": 3.0,
                            "parent": "thigh_l",
                            "nodeType": "joint"
                        },
                        "foot_l": {
                            "tx": -41.7054,
                            "rx": 0.0051,
                            "ry": 2.5398,
                            "rz": 0.1138,
                            "radius": 3.0,
                            "parent": "calf_l",
                            "nodeType": "joint"
                        },
                        "ball_l": {
                            "tx": -6.5368,
                            "ty": -13.6292,
                            "tz": 0.0439,
                            "rz": -90.0,
                            "radius": 3.0,
                            "parent": "foot_l",
                            "nodeType": "joint"
                        },
                        "calf_twist_02_l": {
                            "tx": -13.9018,
                            "tz": -0.05,
                            "rx": 0.005,
                            "ry": -0.2832,
                            "rz": 0.1135,
                            "radius": 3.0,
                            "parent": "calf_l",
                            "nodeType": "joint"
                        },
                        "calf_twist_01_l": {
                            "tx": -27.8036,
                            "tz": -0.1,
                            "rx": 0.005,
                            "ry": -0.2832,
                            "rz": 0.1135,
                            "radius": 3.0,
                            "parent": "calf_l",
                            "nodeType": "joint"
                        },
                        "thigh_twist_01_l": {
                            "tx": -15.2507,
                            "rx": -0.0001,
                            "ry": -0.2833,
                            "rz": 0.0533,
                            "radius": 3.0,
                            "parent": "thigh_l",
                            "nodeType": "joint"
                        },
                        "thigh_twist_02_l": {
                            "tx": -30.5014,
                            "rx": -0.0001,
                            "ry": -0.2833,
                            "rz": 0.0533,
                            "radius": 3.0,
                            "parent": "thigh_l",
                            "nodeType": "joint"
                        },
                        "ik_foot_root": {
                            "radius": 3.0,
                            "parent": "root",
                            "nodeType": "joint"
                        },
                        "ik_foot_l": {
                            "tx": 14.7118,
                            "ty": -0.0415,
                            "tz": 8.1438,
                            "rx": 65.8119,
                            "ry": -89.3347,
                            "rz": -60.6186,
                            "radius": 3.0,
                            "parent": "ik_foot_root",
                            "nodeType": "joint"
                        },
                        "ik_foot_r": {
                            "tx": -14.7118,
                            "ty": -0.0414,
                            "tz": 8.1438,
                            "rx": -114.1877,
                            "ry": 89.3347,
                            "rz": 60.619,
                            "radius": 3.0,
                            "parent": "ik_foot_root",
                            "nodeType": "joint"
                        },
                        "ik_hand_root": {
                            "radius": 3.0,
                            "parent": "root",
                            "nodeType": "joint"
                        },
                        "ik_hand_gun": {
                            "tx": -45.5549,
                            "ty": -14.4006,
                            "tz": 105.6407,
                            "rx": 71.6563,
                            "ry": -51.6072,
                            "rz": 34.7704,
                            "radius": 3.0,
                            "parent": "ik_hand_root",
                            "nodeType": "joint"
                        },
                        "ik_hand_l": {
                            "tx": 46.4804,
                            "ty": -72.0305,
                            "tz": 30.8576,
                            "rx": -145.2021,
                            "ry": -20.2165,
                            "rz": -120.7276,
                            "radius": 3.0,
                            "parent": "ik_hand_gun",
                            "nodeType": "joint"
                        },
                        "ik_hand_r": {
                            "radius": 3.0,
                            "parent": "ik_hand_gun",
                            "nodeType": "joint"
                        },
                        "interaction": {
                            "radius": 3.0,
                            "parent": "root",
                            "nodeType": "joint"
                        },
                        "center_of_mass": {
                            "radius": 3.0,
                            "parent": "root",
                            "nodeType": "joint"
                        }
                    }
                }
            }

        if type == kQuadrupedRoot:
            return {
                "Skeleton": {
                    "Joints": {
                        "Pelvis_Jnt": {
                            "radius": 0.5,
                            "tz": -4.1285,
                            "nodeType": "joint",
                            "parent": "Root_Jnt",
                            "ty": 10.9146
                        },
                        "CannonFront_Rgt_Jnt": {
                            "jox": 1.7534,
                            "radius": 0.5,
                            "tz": -2.7777,
                            "nodeType": "joint",
                            "parent": "Radius_Rgt_Jnt"
                        },
                        "HoofFrontTip_Rgt_Jnt": {
                            "radius": 0.5,
                            "tz": -0.4491,
                            "nodeType": "joint",
                            "parent": "HoofFront_Rgt_Jnt"
                        },
                        "HoofFront_Rgt_Jnt": {
                            "tz": -0.708,
                            "parent": "PasternFront_Rgt_Jnt",
                            "ty": -0.02,
                            "jox": -11.5177,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Scapula_Rgt_Jnt": {
                            "tz": -0.428,
                            "parent": "Shoulder_Jnt",
                            "tx": -1.0706,
                            "ty": 0.4564,
                            "jox": -130.5331,
                            "joy": -1.5141,
                            "joz": 1.2943,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Radius_Rgt_Jnt": {
                            "tz": -2.426,
                            "parent": "Humerus_Rgt_Jnt",
                            "jox": -49.1197,
                            "joz": 180.0,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Neck8_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck7_Jnt"
                        },
                        "Neck7_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck6_Jnt"
                        },
                        "Spine5_Jnt": {
                            "jox": -3.2086,
                            "radius": 0.5,
                            "tz": 1.2891,
                            "nodeType": "joint",
                            "parent": "Spine4_Jnt"
                        },
                        "Neck5_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck4_Jnt"
                        },
                        "Neck4_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck3_Jnt"
                        },
                        "Neck3_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck2_Jnt"
                        },
                        "Neck2_Jnt": {
                            "tz": 0.4277,
                            "parent": "Neck1_Jnt",
                            "ty": 0.2143,
                            "jox": -9.026,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Neck1_Jnt": {
                            "radius": 0.5,
                            "tz": 0.2611,
                            "nodeType": "joint",
                            "parent": "Shoulder_Jnt"
                        },
                        "Eye_Lft_Jnt": {
                            "nodeType": "joint",
                            "tx": 0.7298,
                            "parent": "Head_Jnt",
                            "ty": 0.4374,
                            "radius": 0.5,
                            "tz": 0.587
                        },
                        "HoofBackTip_Lft_Jnt": {
                            "tz": 0.708,
                            "parent": "HoofBack_Lft_Jnt",
                            "ty": 0.02,
                            "jox": -5.1461,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "HoofBack_Lft_Jnt": {
                            "radius": 0.5,
                            "tz": 0.7518,
                            "nodeType": "joint",
                            "parent": "PasternBack_Lft_Jnt"
                        },
                        "PasternBack_Lft_Jnt": {
                            "jox": -32.0856,
                            "radius": 0.5,
                            "tz": 3.5052,
                            "nodeType": "joint",
                            "parent": "CannonBack_Lft_Jnt"
                        },
                        "CannonBack_Lft_Jnt": {
                            "tz": 3.1596,
                            "parent": "Fibula_Lft_Jnt",
                            "jox": -37.8725,
                            "joy": -1.4155,
                            "joz": -1.5105,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Fibula_Lft_Jnt": {
                            "nodeType": "joint",
                            "tx": 0.1987,
                            "parent": "Femur_Lft_Jnt",
                            "jox": 77.9223,
                            "radius": 0.5,
                            "tz": 3.7827
                        },
                        "Spine1_Jnt": {
                            "tz": 0.7968,
                            "parent": "Pelvis_Jnt",
                            "ty": -0.0125,
                            "jox": 8.35,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Tail12_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail11_Jnt"
                        },
                        "Tail10_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail9_Jnt"
                        },
                        "Tail11_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail10_Jnt"
                        },
                        "JawTip_Jnt": {
                            "radius": 0.5,
                            "tz": 2.2192,
                            "nodeType": "joint",
                            "parent": "Jaw_Jnt"
                        },
                        "Jaw_Jnt": {
                            "tz": 0.6392,
                            "parent": "Head_Jnt",
                            "ty": -0.6034,
                            "jox": 4.3305,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Eye_Rgt_Jnt": {
                            "tz": 0.587,
                            "tx": -0.7298,
                            "parent": "Head_Jnt",
                            "ty": 0.4374,
                            "jox": 180.0,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Humerus_Rgt_Jnt": {
                            "tz": -3.9995,
                            "tx": -0.1987,
                            "parent": "Scapula_Rgt_Jnt",
                            "jox": -87.8822,
                            "joz": 180.0,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Spine4_Jnt": {
                            "jox": -3.2086,
                            "radius": 0.5,
                            "tz": 1.2891,
                            "nodeType": "joint",
                            "parent": "Spine3_Jnt"
                        },
                        "Ear_Rgt_Jnt": {
                            "tz": -0.4806,
                            "parent": "Head_Jnt",
                            "tx": -0.7128,
                            "ty": 0.2438,
                            "jox": 135.3,
                            "joz": 17.7,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Root_Jnt": {
                            "nodeType": "joint",
                            "radius": 0.5,
                            "parent": "Joint_Grp"
                        },
                        "Neck6_Jnt": {
                            "radius": 0.5,
                            "tz": 0.9588,
                            "nodeType": "joint",
                            "parent": "Neck5_Jnt"
                        },
                        "HoofFront_Lft_Jnt": {
                            "tz": 0.708,
                            "parent": "PasternFront_Lft_Jnt",
                            "ty": 0.02,
                            "jox": -5.1461,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "CannonFront_Lft_Jnt": {
                            "parent": "Radius_Lft_Jnt",
                            "tz": 2.749,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "PasternFront_Lft_Jnt": {
                            "jox": -30.1682,
                            "radius": 0.5,
                            "tz": 3.0313,
                            "nodeType": "joint",
                            "parent": "CannonFront_Lft_Jnt"
                        },
                        "HeadTip_Jnt": {
                            "radius": 0.5,
                            "tz": 3.6066,
                            "nodeType": "joint",
                            "parent": "Head_Jnt",
                            "ty": -0.1811
                        },
                        "HoofFrontTip_Lft_Jnt": {
                            "radius": 0.5,
                            "tz": 0.4491,
                            "nodeType": "joint",
                            "parent": "HoofFront_Lft_Jnt"
                        },
                        "Scapula_Lft_Jnt": {
                            "tz": -0.428,
                            "parent": "Shoulder_Jnt",
                            "tx": 1.0706,
                            "ty": 0.4564,
                            "jox": 49.4669,
                            "joy": 1.5141,
                            "joz": -1.2943,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Spine2_Jnt": {
                            "jox": -3.209,
                            "radius": 0.5,
                            "tz": 1.2891,
                            "nodeType": "joint",
                            "parent": "Spine1_Jnt"
                        },
                        "Head_Jnt": {
                            "tz": 0.2096,
                            "parent": "Neck8_Jnt",
                            "ty": -0.0333,
                            "jox": 67.609,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "HoofBack_Rgt_Jnt": {
                            "radius": 0.5,
                            "tz": -0.7518,
                            "nodeType": "joint",
                            "parent": "PasternBack_Rgt_Jnt"
                        },
                        "HoofBackTip_Rgt_Jnt": {
                            "tz": -0.708,
                            "parent": "HoofBack_Rgt_Jnt",
                            "ty": -0.02,
                            "jox": -5.1461,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "CannonBack_Rgt_Jnt": {
                            "tz": -3.1596,
                            "parent": "Fibula_Rgt_Jnt",
                            "jox": -37.8932,
                            "joy": -3.199,
                            "joz": -2.4121,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "PasternBack_Rgt_Jnt": {
                            "jox": -32.0856,
                            "radius": 0.5,
                            "tz": -3.5053,
                            "nodeType": "joint",
                            "parent": "CannonBack_Rgt_Jnt"
                        },
                        "Femur_Rgt_Jnt": {
                            "tz": -0.974,
                            "parent": "Pelvis_Jnt",
                            "tx": -1.071,
                            "ty": -0.764,
                            "jox": -130.444,
                            "joy": 2.060,
                            "joz": 1.788,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Fibula_Rgt_Jnt": {
                            "tz": -3.7827,
                            "parent": "Femur_Rgt_Jnt",
                            "tx": -0.1987,
                            "jox": 78.093,
                            "joy": 0.974,
                            "joz": 3.0262,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Radius_Lft_Jnt": {
                            "jox": -49.1201,
                            "radius": 0.5,
                            "tz": 2.426,
                            "nodeType": "joint",
                            "parent": "Humerus_Lft_Jnt"
                        },
                        "Ear_Lft_Jnt": {
                            "tz": -0.4806,
                            "parent": "Head_Jnt",
                            "tx": 0.7128,
                            "ty": 0.2438,
                            "jox": -44.7,
                            "joz": -17.7,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Shoulder_Jnt": {
                            "tz": 1.3656,
                            "parent": "Spine6_Jnt",
                            "ty": 0.0043,
                            "jox": 7.6931,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Humerus_Lft_Jnt": {
                            "tz": 3.9995,
                            "tx": 0.1987,
                            "parent": "Scapula_Lft_Jnt",
                            "jox": 87.8821,
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Tail7_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail6_Jnt"
                        },
                        "EarTip_Rgt_Jnt": {
                            "nodeType": "joint",
                            "radius": 0.5,
                            "parent": "Ear_Rgt_Jnt",
                            "ty": -0.85
                        },
                        "PasternFront_Rgt_Jnt": {
                            "jox": -30.1682,
                            "radius": 0.5,
                            "tz": -3.0313,
                            "nodeType": "joint",
                            "parent": "CannonFront_Rgt_Jnt"
                        },
                        "Spine3_Jnt": {
                            "radius": 0.5,
                            "tz": 1.2891,
                            "nodeType": "joint",
                            "parent": "Spine2_Jnt"
                        },
                        "EarTip_Lft_Jnt": {
                            "nodeType": "joint",
                            "radius": 0.5,
                            "parent": "Ear_Lft_Jnt",
                            "ty": 0.85
                        },
                        "Spine6_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Spine5_Jnt"
                        },
                        "Tail8_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail7_Jnt"
                        },
                        "Tail9_Jnt": {
                            "tz": -0.75,
                            "parent": "Tail8_Jnt",
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Tail4_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail3_Jnt"
                        },
                        "Tail5_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail4_Jnt"
                        },
                        "Tail6_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail5_Jnt"
                        },
                        "Tail3_Jnt": {
                            "radius": 0.5,
                            "tz": -0.75,
                            "nodeType": "joint",
                            "parent": "Tail2_Jnt"
                        },
                        "Tail1_Jnt": {
                            "tz": -1.0,
                            "parent": "Pelvis_Jnt",
                            "radius": 0.5,
                            "nodeType": "joint"
                        },
                        "Tail2_Jnt": {
                            "tz": -0.75,
                            "radius": 0.5,
                            "nodeType": "joint",
                            "parent": "Tail1_Jnt"
                        },
                        "Femur_Lft_Jnt": {
                            "tz": -0.9737,
                            "parent": "Pelvis_Jnt",
                            "tx": 1.0706,
                            "ty": -0.7635,
                            "jox": 49.5564,
                            "joy": -2.0598,
                            "joz": -1.7875,
                            "radius": 0.5,
                            "nodeType": "joint"
                        }
                    }
                }
            }

    def toggle_guides( self, *args ):
        '''
        Toggles the select character between guide and control rig mode.
        :return:
        '''

        sel = mc.ls(sl=True)

        state = None

        # Character list may need to be updated to show the current character in the scene
        if not self.get_active_char():
            self.update_ui()

        if args:
            charRoot = args[0]
        else:
            charRoot = self.get_active_char()

        if not charRoot:
            mc.warning( 'Please select a character in the list.' )
            return False
        else:
            metaData = self.get_metaData( charRoot )
            rigState = None
            type = None

            rigDisplayPrev = None
            rigDisplay = { }

            if 'RigDisplay' in metaData:
                rigDisplayPrev = metaData[ 'RigDisplay' ]

            # We keep this for now for compatibility reasons
            if 'Type' in metaData:
                type = metaData[ 'Type' ]
            if 'RigType' in metaData:
                type = metaData[ 'RigType' ]

            displayAttrs = [ 'show_Joints', 'show_Rig', 'show_Guides', 'display_Joint', 'display_Geo' ]

            for displayAttr in displayAttrs:
                try:
                    rigDisplay[ displayAttr ] = mc.getAttr( charRoot + '.' + displayAttr )
                except:
                    mc.warning( 'Can not get attribute ', charRoot + '.' + displayAttr )
                    pass

            metaData[ 'RigDisplay' ] = rigDisplay

            # Save the current settings
            self.set_metaData( charRoot, metaData )

            self.build_main_attrs( charRoot )

            if 'RigState' in metaData:

                mc.undoInfo( openChunk = True )
                rigState = metaData[ 'RigState' ]

                # Adjust Control Scale to global scale
                s = mc.getAttr( charRoot + '.globalScale' )
                try:
                    mc.setAttr( charRoot + '.globalCtrlScale', s )
                except:
                    pass

                # Switch to Guide Mode
                if rigState == kRigStateControl:

                    handles = self.get_char_handles( charRoot, { 'Type': kHandle } )
                    handleDict = { }

                    if handles:
                        for handle in handles:

                            handle = self.find_node( charRoot, handle )

                            handleShort = self.short_name( handle )

                            handleDict[ handleShort ] = self.get_attributes( handle, getAnimKeys = False )

                            for attr in handleDict[ handleShort ].keys():

                                if handleDict[ handleShort ][ attr ][ 'input' ] == 'animCurve':

                                    src = handleDict[ handleShort ][ attr ][ 'animCurve' ] + '.output'
                                    if not mc.objExists( src ):
                                        mc.warning( 'aniMeta: source does not exist', src )

                                    dst = handle + '.' + attr
                                    if not mc.objExists( dst ):
                                        mc.warning( 'aniMeta: dest does not exist', dst )

                                    if mc.isConnected( src, dst ):
                                        try:
                                            mc.disconnectAttr( src, dst )
                                        except:
                                            pass
                                    else:
                                        mc.warning( 'Not connected:', src, dst )
                    metaData[ 'GuidePose' ] = handleDict

                    self.set_metaData( charRoot, metaData )
                    # delete control rig
                    self.delete_controls( charRoot )

                    if type == kBiped or type == kBipedUE:
                        self.delete_mocap( charRoot )

                    # create guides
                    skipExistingGuides = True
                    self.build_body_guides( charRoot, type, skipExistingGuides )

                    om.MGlobal.displayInfo( 'aniMeta: ' + charRoot + ' is now in guide mode.' )

                    # Set the previous values to the display attributes
                    if rigDisplayPrev is not None:
                        for key in rigDisplayPrev.keys():
                            try:
                                mc.setAttr( charRoot + '.' + key, rigDisplayPrev[ key ] )
                            except:
                                pass

                    mc.setAttr( charRoot + '.show_Guides', True )
                    mc.setAttr( charRoot + '.show_Joints', True )

                    state= kRigStateGuide

                # Switch to Control Mode
                elif rigState == kRigStateGuide:

                    # delete guides
                    # Dont delete the actual guides because we need them for rigging
                    self.delete_body_guides( charRoot, deleteOnlyConstraints=True )

                    # create control rig
                    if type == kBiped or type == kBipedUE:
                        biped = Biped()
                        biped.build_control_rig( charRoot )
                        biped.build_mocap( charRoot, type )

                    if type == kQuadruped:
                        self.rig_control_quadruped_create()

                    om.MGlobal.displayInfo( 'aniMeta: ' + charRoot + ' is now in control rig mode.' )

                    # Set the previous values to the display attributes
                    if rigDisplayPrev is not None:
                        for key in rigDisplayPrev.keys():
                            try:
                                mc.setAttr( charRoot + '.' + key, rigDisplayPrev[ key ] )
                            except:
                                pass

                    metaData = self.get_metaData( charRoot )

                    if 'GuidePose' in metaData:
                        pose = metaData[ 'GuidePose' ]

                        for handle in pose.keys():
                            handle_long = self.find_node(charRoot, handle)
                            for attr in pose[ handle ].keys():
                                if pose[ handle ][ attr ][ 'input' ] == 'static':
                                    if pose[ handle ][ attr ][ 'dataType' ] == 'enum':
                                        pass
                                    else:
                                        self.set_attr( handle_long, attr, pose[ handle ][ attr ][ 'value' ] )

                                if pose[ handle ][ attr ][ 'input' ] == 'animCurve':

                                    src = pose[ handle ][ attr ][ 'animCurve' ] + '.output'
                                    if not mc.objExists( src ):
                                        mc.warning( 'aniMeta: source does not exist', src )

                                    dst = handle_long + '.' + attr
                                    if not mc.objExists( dst ):
                                        mc.warning( 'aniMeta: dest does not exist', dst )

                                    if mc.objExists( src ) and mc.objExists( dst ):
                                        if not mc.isConnected( src, dst ):
                                            try:
                                                mc.connectAttr( src, dst, f = True )
                                            except:
                                                pass
                                        else:
                                            mc.warning( 'Not connected:', src, dst )

                    mc.setAttr( charRoot + '.show_Guides', False )
                    mc.setAttr( charRoot + '.show_Joints', True )

                    state= kRigStateControl

                mc.undoInfo( closeChunk = True )
                self.update_ui(rig=charRoot)
                mc.select(sel)
                return state

# Char
#
######################################################################################


######################################################################################
#
# Biped

class Biped( Char ):

    def __init__(self):
        super( Biped, self ).__init__()

        self.DEBUG = False

    def build_control_rig( self, *args ):

        handleDict = {}
        controls   = {}          # Store the DAG Paths of created controls
        metaData   = {}
        rootNode   = None
        rigState   = None
        type       = None
        fingers = ['Index', 'Middle', 'Ring', 'Pinky', 'Thumb']
        SIDES = [ 'Lft', 'Rgt' ]
        sides = [ 'l', 'r' ]
        colors = [ [ 0, 0, 1 ], [ 1, 0, 0 ] ]
        multi = [ 1, -1 ]

        if len( args ):
            rootNode = args[0]
        else:
            rootNode = self.get_active_char()

        if rootNode is None:
            mc.warning('aniMeta: No Valid character specified. Aborting rig build.')
            return False

        ctrlsDict = {}
        ctrlsDict['character']      = rootNode
        ctrlsDict['globalScale']    = True
        ctrlsDict['shapeType']      = self.kCube
        ctrlsDict['showRotateOrder']= True
        ctrlsDict['rotateOrder']    = kZXY
        ctrlsDict['createBlendGrp'] = True
        ctrlsDict['colors']         = (1,1,0)

        if rootNode is None:
            mc.warning('aniMeta: Please select a character`s root group.')
        else:
            rootData = self.get_metaData(rootNode)

            if 'RigState' in rootData:
                rigState = rootData['RigState']

            # We leave the first variant here for now for compatibility reasons
            if 'Type' in rootData:
                type = rootData['Type']
            if 'RigType' in rootData:
                type = rootData['RigType']

            delete_body_guides = False

            if rigState == kRigStateControl:
                mc.warning('aniMeta: The rig already is already in control mode.')
                return

            rootData['RigState'] = kRigStateControl

            self.set_metaData( rootNode, rootData )

            offset = om.MEulerRotation(math.radians(180.0), 0.0, 0.0, 0).asMatrix()

            def getParent(obj, index):
                if obj is not None:
                    if len (obj) > 0 and index < len(obj)-1:
                        return obj[index]
                return None

            rig_grp = self.find_node(rootNode,'Rig_Grp')

            global_scale = mc.getAttr( rootNode + '.globalScale' )

            prx_grp = self.find_node( rootNode, 'Proxy_Grp' )
            if prx_grp is None:
                prx_grp = mc.createNode( 'transform', name='Proxy_Grp', ss=True, parent = 'Offset_Grp' )
            mc.setAttr( prx_grp + '.v', False )
            prx_grp = self.get_path( prx_grp )

            # Connect nodes to this attribute for housecleaning that don`t get deleted when the rig is deleted
            aux_nodes_attr = 'aux_nodes'
            if not mc.attributeQuery( aux_nodes_attr, node=rootNode,exists=True):
                mc.addAttr( rootNode, longName= aux_nodes_attr, at='message')

            def save_for_cleanup( node ):
                mc.addAttr( node, longName = aux_nodes_attr, at='message' )
                mc.connectAttr( rootNode+'.'+aux_nodes_attr, node+'.'+aux_nodes_attr )

            if self.DEBUG:
                print ('Create Controls')

            ########################################################################################################
            #
            # Delete Guides
            self.delete_body_guides( rootNode, deleteOnlyConstraints=True )

            # Delete SymConstraints in Proxy Grp
            nodes = mc.listRelatives( self.find_node(rootNode, prx_grp), pa=True)
            if nodes is not None:
                for node in nodes:
                    con = mc.listConnections( node + '.t', s=True, d=False)
                    if con:
                        mc.delete( con )

            # Delete Guides
            #
            ########################################################################################################

            #######################################################################################################
            #
            # Joint Mapping

            joints  = {}

            if type == kBiped:
                leg_preferred_angle = [ 45,0,0 ]
                arm_preferred_angle = [ 0,-45,0 ]

                joints['Root_Ctr']    = self.get_path( self.find_node( rootNode, 'Root_Jnt' ))
                joints['Hips_Ctr']    = self.get_path( self.find_node( rootNode, 'Hips_Jnt' ))
                joints['Spine1_Ctr']  = self.get_path( self.find_node( rootNode, 'Spine1_Jnt' ))
                joints['Spine2_Ctr']  = self.get_path( self.find_node( rootNode, 'Spine2_Jnt' ))
                joints['Spine3_Ctr']  = self.get_path( self.find_node( rootNode, 'Spine3_Jnt' ))
                joints['Chest_Ctr']   = self.get_path( self.find_node( rootNode, 'Chest_Jnt' ))
                joints['Neck_Ctr']    = self.get_path( self.find_node( rootNode, 'Neck_Jnt' ))
                joints['Head_Ctr']    = self.get_path( self.find_node( rootNode, 'Head_Jnt' ))
                joints['Jaw_Ctr']     = self.get_path( self.find_node( rootNode, 'Jaw_Jnt' ))

                for i in range( 2 ):

                    joints[ 'LegUp_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'LegUp_'+SIDES[i]+'_Jnt' ))
                    joints[ 'LegLo_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'LegLo_'+SIDES[i]+'_Jnt' ))
                    joints[ 'Foot_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'Foot_'+SIDES[i]+'_Jnt' ))
                    joints[ 'Toes_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'Toes_'+SIDES[i]+'_Jnt' ))
                    joints[ 'ArmUp_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'ArmUp_'+SIDES[i]+'_Jnt' ))
                    joints[ 'ArmLo_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'ArmLo_'+SIDES[i]+'_Jnt' ))
                    joints[ 'Hand_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'Hand_'+SIDES[i]+'_Jnt' ))
                    joints[ 'Clavicle_'  + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'Clavicle_'+SIDES[i]+'_Jnt' ))

            if type == kBipedUE:

                offset_rot   = om.MEulerRotation( 0, math.radians( 90 ), math.radians( -90 ) )
                offset_rot_2 = om.MEulerRotation(  math.radians( 90 ), 0, 0 )
                offset_rot_3 = om.MEulerRotation(  math.radians( 180 ), 0, 0 )
                leg_preferred_angle = [ 0,0,-45 ]
                arm_preferred_angle = [ 0,-45,0 ]

                joints['Root_Ctr']    = self.get_path( self.find_node( rootNode, 'root' ))
                joints['Hips_Ctr']    = self.get_path( self.find_node( rootNode, 'pelvis' ))
                joints['Spine1_Ctr']  = self.get_path( self.find_node( rootNode, 'spine_01' ))
                joints['Spine2_Ctr']  = self.get_path( self.find_node( rootNode, 'spine_02' ))
                joints['Spine3_Ctr']  = self.get_path( self.find_node( rootNode, 'spine_03' ))
                joints['Spine4_Ctr']  = self.get_path( self.find_node( rootNode, 'spine_04' ))
                joints['Spine5_Ctr']  = self.get_path( self.find_node( rootNode, 'spine_05' ))
                joints['Chest_Ctr']   = None
                joints['Neck_Ctr']    = self.get_path( self.find_node( rootNode, 'neck_01' ))
                joints['Neck2_Ctr']   = self.get_path( self.find_node( rootNode, 'neck_02' ))
                joints['Head_Ctr']    = self.get_path( self.find_node( rootNode, 'head' ))
                joints['Jaw_Ctr']     = None

                for i in range( 2 ):

                    joints[ 'LegUp_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'thigh_'    +sides[i] ))
                    joints[ 'LegLo_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'calf_'     +sides[i] ))
                    joints[ 'Foot_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'foot_'     +sides[i] ))
                    joints[ 'Toes_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'ball_'     +sides[i] ))
                    joints[ 'ArmUp_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'upperarm_' +sides[i] ))
                    joints[ 'ArmLo_'     + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'lowerarm_' +sides[i] ))
                    joints[ 'Hand_'      + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'hand_'     +sides[i] ))
                    joints[ 'Clavicle_'  + SIDES[i] ] = self.get_path( self.find_node( rootNode, 'clavicle_' +sides[i] ))

            # Joint Mapping
            #
            #######################################################################################################

            # Create Handle

            hand_space_switch_list = [ 'Main_Ctr_Ctrl', 'Head_Ctr_Ctrl','Spine3_Ctr_Ctrl', 'Hips_Ctr_Ctrl', 'Torso_Ctr_Ctrl' ]
            if type ==kBipedUE:
                hand_space_switch_list[2] = 'Spine5_Ctr_Ctrl'

            handleDict[ 'Torso_Ctr_Ctrl' ] = {
                'name': 'Torso_Ctr_Ctrl',
                'parent': 'Main_Ctr_Ctrl',
                'matchTransform': 'Hips_Guide',
                'size': [ 6, 6, 30 ]
            }
            handleDict[ 'Hips_Ctr_Ctrl' ] = {
                'name': 'Hips_Ctr_Ctrl',
                'parent': 'Torso_Ctr_Ctrl',
                'matchTransform': 'Spine1_Guide',
                'size': [ 2, 20, 20 ],
                'constraint': self.kParent,
                'constraintNode': joints['Hips_Ctr'],
                'maintainOffset': True
            }
            handleDict[ 'Spine1_Ctr_Ctrl' ] = {
                'name': 'Spine1_Ctr_Ctrl',
                'parent': 'Torso_Ctr_Ctrl',
                'matchTransform': 'Spine1_Guide',
                'size': [ 2, 2, 20 ],
                'constraint': self.kParent,
                'constraintNode': joints['Spine1_Ctr'] ,
                'maintainOffset': True
            }
            handleDict[ 'Spine2_Ctr_Ctrl' ] = {
                'name': 'Spine2_Ctr_Ctrl',
                'parent': 'Spine1_Ctr_Ctrl',
                'matchTransform': 'Spine2_Guide',
                'size': [ 2, 2, 20 ],
                'constraint': self.kParent,
                'constraintNode':  joints['Spine2_Ctr'],
                'maintainOffset': True
            }
            handleDict[ 'Spine3_Ctr_Ctrl' ] = {
                'name': 'Spine3_Ctr_Ctrl',
                'parent': 'Spine2_Ctr_Ctrl',
                'matchTransform': 'Spine3_Guide',
                'size': [ 2, 2, 20 ],
                'constraint': self.kParent,
                'constraintNode':  joints['Spine3_Ctr'] ,
                'maintainOffset': True
            }
            if type == kBiped:
                handleDict[ 'Chest_Ctr_Ctrl' ] = {
                    'name': 'Chest_Ctr_Ctrl',
                    'parent': 'Spine3_Ctr_Ctrl',
                    'matchTransform': 'Chest_Guide',
                    'size': [ 25, 4, 4 ],
                    'constraint': self.kParent,
                    'constraintNode':  joints['Chest_Ctr'] ,
                    'maintainOffset': True
                }
                handleDict[ 'Jaw_Ctr_Ctrl' ] = {
                    'name': 'Jaw_Ctr_Ctrl',
                    'parent': 'Head_Ctr_Ctrl',
                    'matchTransform': 'Jaw_Guide',
                    'size': [ 25, 4, 4 ],
                    'constraint': self.kParent,
                    'constraintNode':  joints['Jaw_Ctr'] ,
                    'maintainOffset': True
                }
                handleDict[ 'Neck_Ctr_Ctrl' ] = {
                    'name': 'Neck_Ctr_Ctrl',
                    'parent': 'Chest_Ctr_Ctrl',
                    'matchTransform': 'Neck_Guide',
                    'size': [ 20, 2, 2 ],
                    'constraint': self.kParent,
                    'constraintNode':joints['Neck_Ctr'],
                    'maintainOffset': True
                }

                handleDict[ 'Head_Ctr_Ctrl' ] = {
                    'name': 'Head_Ctr_Ctrl',
                    'parent': 'Neck_Ctr_Ctrl',
                    'matchTransform': 'Head_Guide',
                    'size': [ 20, 2, 2 ],
                    'constraint': self.kParent,
                    'constraintNode':joints['Head_Ctr'],
                    'maintainOffset': True
                }
            if type == kBipedUE:
                handleDict['Spine4_Ctr_Ctrl'] = {
                    'name': 'Spine4_Ctr_Ctrl',
                    'parent': 'Spine3_Ctr_Ctrl',
                    'matchTransform': 'Spine4_Guide',
                    'size': [2, 2, 20],
                    'constraint': self.kParent,
                    'constraintNode': joints['Spine4_Ctr'],
                    'maintainOffset': True
                }
                handleDict['Spine5_Ctr_Ctrl'] = {
                    'name': 'Spine5_Ctr_Ctrl',
                    'parent': 'Spine4_Ctr_Ctrl',
                    'matchTransform': 'Spine5_Guide',
                    'size': [2, 2, 20],
                    'constraint': self.kParent,
                    'constraintNode': joints['Spine5_Ctr'],
                    'maintainOffset': True
                }

                handleDict[ 'Neck1_Ctr_Ctrl' ] = {
                    'name': 'Neck1_Ctr_Ctrl',
                    'parent': 'Spine5_Ctr_Ctrl',
                    'matchTransform': 'Neck1_Guide',
                    'size': [ 2, 2, 20 ],
                    'constraint': self.kParent,
                    'constraintNode':joints['Neck_Ctr'],
                    'maintainOffset': True
                }

                handleDict['Neck2_Ctr_Ctrl'] = {
                    'name': 'Neck2_Ctr_Ctrl',
                    'parent': 'Neck1_Ctr_Ctrl',
                    'matchTransform': 'Neck2_Guide',
                    'size': [2, 2, 20],
                    'constraint': self.kParent,
                    'constraintNode': joints['Neck2_Ctr'],
                    'maintainOffset': True
                }

                handleDict[ 'Head_Ctr_Ctrl' ] = {
                    'name': 'Head_Ctr_Ctrl',
                    'parent': 'Neck2_Ctr_Ctrl',
                    'matchTransform': 'Head_Guide',
                    'size': [ 2, 2, 20 ],
                    'constraint': self.kParent,
                    'constraintNode':joints['Head_Ctr'],
                    'maintainOffset': True
                }

            handleDict[ 'Root_Ctr_Ctrl' ] = {
                'name': 'Root_Ctr_Ctrl',
                'parent': 'Main_Ctr_Ctrl',
                'matchTransform': 'root',
                'size': [ 5, 5, 5 ],
                'constraint': self.kParent,
                'constraintNode':joints['Root_Ctr'],
                'maintainOffset': True
            }
            for i in range( 2 ):

                handleDict[ 'Foot_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Foot_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Main_Ctr_Ctrl',
                    'matchTransform': 'Foot_' + SIDES[ i ] + '_Guide',
                    'size': [ 5, 5, 5 ],
                    'color': colors[ i ]
                }
                if i == 1:
                    offset_matrix = Transform().create_matrix( rotate=om.MEulerRotation( math.radians(180),0,0 ))
                    handleDict[ 'Foot_IK_' + SIDES[ i ] + '_Ctrl' ]['offsetMatrix'] = offset_matrix

                handleDict[ 'Heel_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Heel_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Foot_IK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Heel_' + SIDES[ i ] + '_Guide',
                    'size': [ 2, 2, 12 ],
                    'rotateOrder': kXYZ,
                    'color': colors[ i ]
                }
                handleDict[ 'ToesTip_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'ToesTip_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Heel_IK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'ToesTip_' + SIDES[ i ] + '_Guide',
                    'size': [ 2, 2, 12 ],
                    'rotateOrder': kXYZ,
                    'color': colors[ i ]
                }
                handleDict[ 'Toes_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Toes_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'ToesTip_IK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Ball_' + SIDES[ i ] + '_Guide',
                    'size': [ 2, 2, 12 ],
                    'rotateOrder': kXYZ,
                    'color': colors[ i ]
                }
                handleDict[ 'FootLift_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'FootLift_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'ToesTip_IK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Ball_' + SIDES[ i ] + '_Guide',
                    'size': [ 2, 2, 12 ],
                    'rotateOrder': kXYZ,
                    'color': colors[ i ],
                    'offset': (-6 * global_scale * multi[ i ], 3 * global_scale * multi[ i ],0 ),
                    'rotate': (0, 0, 30)
                }
                handleDict[ 'LegPole_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'LegPole_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Foot_IK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'LegLo_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kCube,
                    'size': [ 2, 2, 2 ]
                }
                handleDict[ 'HipsUpVec_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'HipsUpVec_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Hips_Ctr_Ctrl',
                    'matchTransform': 'Hips_' + SIDES[ i ] + '_upVec_Guide',
                    'shapeType': self.kSphere,
                    'radius': 2,
                    'rotateOrder': kXYZ,
                    'color': colors[ i ],
                    'constraint': self.kParent,
                    'constraintNode':'Hips_' + SIDES[ i ] + '_upVec',
                    'maintainOffset': False
                }
                handleDict[ 'Clavicle_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Clavicle_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Chest_Ctr_Ctrl',
                    'matchTransform': 'Clavicle_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'size': [ 2, 20, 2 ],
                    'offset': (3 * global_scale * multi[ i ], 0, 0)
                }
                if type == kBipedUE:
                    handleDict[ 'Clavicle_' + SIDES[ i ] + '_Ctrl' ][ 'parent' ] = 'Spine5_Ctr_Ctrl'

                handleDict[ 'ShoulderUpVec_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'ShoulderUpVec_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Clavicle_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Shoulder_' + SIDES[ i ] + '_upVec_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 2,
                    'constraint': self.kParent,
                    'constraintNode':'Shoulder_' + SIDES[ i ] + '_upVec',
                    'maintainOffset': False
                }
                handleDict[ 'ArmUp_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'ArmUp_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Clavicle_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'ArmUp_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 6
                }
                handleDict[ 'ArmLo_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'ArmLo_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'ArmUp_FK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'ArmLo_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4
                }
                handleDict[ 'Hand_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Hand_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'ArmLo_FK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Hand_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4,
                    'constraint': self.kParent,
                    'constraintNode':joints[ 'Hand_' + SIDES[i] ] ,
                    'maintainOffset': True
                }
                for j in range( len( fingers ) ):

                    for k in range( 1, 5 ):

                        if fingers[j] == 'Thumb' and k==4:
                            continue

                        finger_dict = {
                            'name': fingers[ j ] + str( k ) + '_' + SIDES[ i ] + '_Ctrl',
                            'matchTransform':  fingers[ j ] + str( k ) + '_' + SIDES[ i ] + '_Guide',
                            'color':           colors[ i ],
                            'shapeType':       self.kSphere,
                            'radius':          1.5,
                            'constraintNode':  fingers[ j ] + str( k ) + '_' + SIDES[ i ] + '_Jnt',
                            'maintainOffset':  True,
                            'constraint':      self.kParent
                        }
                        if k == 1:
                            if fingers[j] == 'Thumb':
                                finger_dict[ 'parent' ] = 'Hand_FK_' + SIDES[ i ] + '_Ctrl'
                            else:
                                if type == kBipedUE:
                                    finger_dict['parent'] = fingers[ j ] +'Meta_' + SIDES[i] + '_Ctrl'
                                else: 
                                    finger_dict[ 'parent' ] = 'Hand_FK_' + SIDES[ i ] + '_Ctrl'
                        else:
                            finger_dict[ 'parent' ] = fingers[ j ] + str( k - 1 ) + '_' + SIDES[ i ] + '_Ctrl'

                        if type == kBipedUE:
                            name = fingers[ j ].lower() + '_0'+str( k ) + '_' + sides[i]
                            finger_dict[ 'constraintNode' ] = self.get_path( self.find_node( rootNode, name ))

                        handleDict[ fingers[ j ] + str( k ) + '_' + SIDES[ i ] + '_Ctrl' ] = finger_dict

                if type == kBipedUE:

                    for j in range(4):
                        finger_dict = {
                            'name': fingers[j] + 'Meta_' + SIDES[i] + '_Ctrl',
                            'parent': 'Hand_FK_' + SIDES[ i ] + '_Ctrl',
                            'matchTransform': fingers[j] + 'Meta_' + SIDES[i] + '_Guide',
                            'color': colors[i],
                            'shapeType': self.kSphere,
                            'radius': 1.5,
                            'constraintNode': fingers[j].lower()  +  '_metacarpal_' + sides[i],
                            'maintainOffset': True,
                            'constraint': self.kParent
                        }
                        handleDict[ fingers[ j ] + 'Meta_' + SIDES[ i ] + '_Ctrl' ] = finger_dict


                handleDict[ 'LegUp_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'LegUp_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Hips_Ctr_Ctrl',
                    'matchTransform': 'LegUp_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4
                }
                handleDict[ 'LegLo_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'LegLo_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'LegUp_FK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'LegLo_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4
                }
                handleDict[ 'Foot_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Foot_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'LegLo_FK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Foot_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4
                }
                handleDict[ 'Toes_FK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Toes_FK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Foot_FK_' + SIDES[ i ] + '_Ctrl',
                    'matchTransform': 'Ball_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kSphere,
                    'radius': 4
                }
                handleDict[ 'Hand_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'Hand_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Main_Ctr_Ctrl',
                    'matchTransform': 'Hand_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kCube,
                    'size': [ 2, 10, 2 ]
                }
                handleDict[ 'ArmPole_IK_' + SIDES[ i ] + '_Ctrl' ] = {
                    'name': 'ArmPole_IK_' + SIDES[ i ] + '_Ctrl',
                    'parent': 'Main_Ctr_Ctrl',
                    'matchTransform': 'ArmLo_' + SIDES[ i ] + '_Guide',
                    'color': colors[ i ],
                    'shapeType': self.kCube,
                    'size': [ 2, 2, 2 ]
                }


            ########################################################################################################
            #
            # Centre

            if self.DEBUG:
                print ('Build Centre')

            # Main
            ctrlDict                   = copy.deepcopy( ctrlsDict )
            ctrlDict['name']           = 'Main_Ctr_Ctrl'
            ctrlDict['shapeType']      = self.kPipe
            ctrlDict['thickness']      = 3*global_scale
            ctrlDict['radius']         = 40
            ctrlDict['height']         = 1
            ctrlDict['color']          = (1,1,0)
            ctrlDict['globalScale']    = True
            ctrlDict['scale']          = global_scale
            ctrlDict['createBlendGrp'] = True
            controls['Main_Ctr_Ctrl']  = self.create_handle( **ctrlDict )

            # We have to parent this one manually
            parent = mc.listRelatives( controls['Main_Ctr_Ctrl'].fullPathName(), p=True, pa=True )[0]
            parent = mc.listRelatives( parent, p=True, pa=True )[0]
            mc.parent( parent, rig_grp )

            if type == kBiped:
                controlsList = [
                    'Torso_Ctr_Ctrl',
                    'Hips_Ctr_Ctrl',
                    'Spine1_Ctr_Ctrl',
                    'Spine2_Ctr_Ctrl',
                    'Spine3_Ctr_Ctrl',
                    'Chest_Ctr_Ctrl',
                    'Neck_Ctr_Ctrl',
                    'Head_Ctr_Ctrl',
                    'Jaw_Ctr_Ctrl',
                    'Root_Ctr_Ctrl'
                ]
            elif type == kBipedUE:
                controlsList = [
                    'Torso_Ctr_Ctrl',
                    'Hips_Ctr_Ctrl',
                    'Spine1_Ctr_Ctrl',
                    'Spine2_Ctr_Ctrl',
                    'Spine3_Ctr_Ctrl',
                    'Spine4_Ctr_Ctrl',
                    'Spine5_Ctr_Ctrl',
                    'Neck1_Ctr_Ctrl',
                    'Neck2_Ctr_Ctrl',
                    'Head_Ctr_Ctrl',
                    'Jaw_Ctr_Ctrl',
                    'Root_Ctr_Ctrl'
                ]



            for SIDE in [ 'Lft', 'Rgt' ]:
                controlsList.append( 'Foot_IK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'Heel_IK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'ToesTip_IK_'+SIDE+'_Ctrl'    )
                controlsList.append( 'Toes_IK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'FootLift_IK_'+SIDE+'_Ctrl'   )
                controlsList.append( 'LegPole_IK_'+SIDE+'_Ctrl'    )
                controlsList.append( 'HipsUpVec_'+SIDE+'_Ctrl'     )
                controlsList.append( 'Clavicle_'+SIDE+'_Ctrl'      )
                controlsList.append( 'ArmUp_FK_'+SIDE+'_Ctrl'      )
                controlsList.append( 'ArmLo_FK_'+SIDE+'_Ctrl'      )
                controlsList.append( 'Hand_FK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'ShoulderUpVec_'+SIDE+'_Ctrl' )
                controlsList.append( 'LegUp_FK_'+SIDE+'_Ctrl'      )
                controlsList.append( 'LegLo_FK_'+SIDE+'_Ctrl'      )
                controlsList.append( 'Foot_FK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'Toes_FK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'Hand_IK_'+SIDE+'_Ctrl'       )
                controlsList.append( 'ArmPole_IK_'+SIDE+'_Ctrl'    )

                if type == kBiped:
                    for finger in fingers:
                        for i in range(1,5):
                            if finger == 'Thumb' and i == 4:
                                continue
                            controlsList.append( finger+str(i)+'_'+SIDE+'_Ctrl' )

                elif type == kBipedUE:
                    for finger in fingers:

                        controlsList.append( finger+'Meta_'+SIDE+'_Ctrl' )

                        for i in range(1,4):
                            controlsList.append( finger+str(i)+'_'+SIDE+'_Ctrl' )

            # Loop over dictionary to build the actual controls
            for control in controlsList:
                if control in handleDict:
                    # Create a copy of the standard dict
                    ctrlDict = copy.deepcopy( ctrlsDict )

                    # Update the copy with the specifics
                    ctrlDict.update( handleDict[control] )

                    # Build the control
                    controls[control]           = self.create_handle( **ctrlDict )

            if type == kBiped:
                if 'Jaw_Ctr_Ctrl' in handleDict:

                    # Jaw
                    '''
                    ctrlDict                    = copy.deepcopy( ctrlsDict )
                    ctrlDict['name']            = 'Jaw_Ctr_Ctrl'
                    ctrlDict['matchTransform']  = handleDict['Jaw_Ctr_Ctrl']['joint']
                    ctrlDict['offsetMatrix']    = handleDict['Jaw_Ctr_Ctrl']['offsetMatrix']
                    ctrlDict['parent']          = controls['Head_Ctr_Ctrl']
                    ctrlDict['shapeType']       = self.kCube
                    ctrlDict['width']           = handleDict['Jaw_Ctr_Ctrl']['size'][0]
                    ctrlDict['height']          = handleDict['Jaw_Ctr_Ctrl']['size'][1]
                    ctrlDict['depth']           = handleDict['Jaw_Ctr_Ctrl']['size'][2]
                    ctrlDict['showRotateOrder'] = True
                    ctrlDict['rotateOrder']     = kZXY
                    ctrlDict['createBlendGrp']  = True'''
                    #controls['Jaw_Ctr_Ctrl']    = self.create_handle( **handleDict['Jaw_Ctr_Ctrl'] )

            if self.DEBUG:
                print ('Build Centre completed')

            # Centre
            #
            ########################################################################################################


            ########################################################################################################
            #
            # Spine

            def create_constraint( target, node ):
                mc.parentConstraint( target,  node,  mo=True )
                mc.scaleConstraint(  target,  node,  mo=True )

            if type == kBiped:
                create_constraint( controls['Hips_Ctr_Ctrl'].fullPathName(), self.find_node( rootNode,  'Hips_Jnt' ) )
                create_constraint( controls['Spine1_Ctr_Ctrl'].fullPathName(), self.find_node( rootNode,  'Spine1_Jnt' )   )
                create_constraint( controls['Spine2_Ctr_Ctrl'].fullPathName(), self.find_node( rootNode,  'Spine2_Jnt' )   )
                create_constraint( controls['Spine3_Ctr_Ctrl'].fullPathName(), self.find_node( rootNode,  'Spine3_Jnt' )  )

             # Spine
            #
            ########################################################################################################

            ######################################################################################
            #
            # Position Pole Vectors

            if self.DEBUG:
                print ( 'Position Pole Vectors' )

            poles = ['LegPole_IK_', 'ArmPole_IK_']

            root_ctrls = ['LegUp_FK_', 'ArmUp_FK_']
            eff_ctrls  = ['LegLo_FK_', 'ArmLo_FK_']
            hndl_ctrls  = ['Foot_FK_', 'Hand_FK_']

            for SIDE in [ 'Lft', 'Rgt'  ]:

                for i in range( len ( poles ) ):

                    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'  ]:
                        mc.setAttr( controls[poles[i]+SIDE+'_Ctrl'].fullPathName()+ '.'+attr, l=False)

                    #legUp_jnt = controls[ root_ctrls[i]+SIDE+'_Ctrl' ]
                    #legLo_jnt = controls[ eff_ctrls[i] +SIDE+'_Ctrl' ]
                    #foot_jnt  = controls[ hndl_ctrls[i]+SIDE+'_Ctrl' ]

                    #legUp_jnt = self.find_node( controls[ root_ctrls[i]+SIDE+'_Ctrl' ] )
                    legLo_jnt = controls[ eff_ctrls[i] +SIDE+'_Ctrl' ]
                    foot_jnt  = controls[ hndl_ctrls[i]+SIDE+'_Ctrl' ]

                    # Redundant? Wird beim IK Setup besser passen...
                    '''
                    pole_matrix = self.get_polevector_position( legUp_jnt, legLo_jnt, foot_jnt, preferred_angle )

                    parent = mc.listRelatives ( controls[ poles[i]+SIDE+'_Ctrl' ].fullPathName(), p=True )[0]
                    parent = mc.listRelatives ( parent, p=True )[0]

                    self.set_matrix( parent, pole_matrix, kWorld)

                    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'  ]:
                        mc.setAttr( parent + '.'+attr, l=True)
                    '''
            if self.DEBUG:
                print ( 'Position Pole Vector done' )

            # Position Pole Vector
            #
            ######################################################################################

            internal_grp = mc.createNode( 'transform', name='Internal_Grp', parent= self.find_node(rootNode, 'Rig_Grp' ) )
            grp = mc.createNode( 'transform', name='IKFoot_Grp', parent=internal_grp )
            mc.setAttr( internal_grp + '.v', False )
            mc.setAttr( internal_grp + '.inheritsTransform', False )

            # Legs
            #
            ########################################################################################################

            ######################################
            #
            # Eyes
            if type == kBiped:
                eyes_grp = mc.createNode( 'transform', name='Eyes_Grp', parent= controls['Main_Ctr_Ctrl']  , ss=True )

                Eyes_Ctr_Ctrl = self.create_handle( name='Eyes_Ctr_Ctrl', matchTransform=self.find_node(rootNode, 'Eye_Lft_Jnt'), parent = eyes_grp,
                                             shapeType=self.kCube, green=1, red=1, width=3, height=3, depth=3,   character = rootNode, globalScale = True )

                eye_ctrl_grp = mc.listRelatives( Eyes_Ctr_Ctrl.fullPathName(), p=True, pa=True )[0]
                mc.setAttr( eye_ctrl_grp + '.tx', l=0 )
                mc.setAttr( eye_ctrl_grp + '.tz', l=0 )

                # Move the control to the centre
                mc.setAttr( eye_ctrl_grp + '.tx',  0 )

                Eyes_Lft_Ctrl = self.create_handle(name='Eye_Lft_Ctrl', matchTransform=self.find_node(rootNode, 'Eye_Lft_Jnt'),   parent =  Eyes_Ctr_Ctrl.fullPathName()  ,
                                             shapeType=self.kCube, color=colors[0], width=2, height=2, depth=2,   character = rootNode, globalScale = True,
                                             constraint=self.kAim, aimVec=(0,0,1), upVec = (0,1,0))

                Eyes_Rgt_Ctrl = self.create_handle(name='Eye_Rgt_Ctrl', matchTransform=self.find_node(rootNode, 'Eye_Rgt_Jnt'),   parent = Eyes_Ctr_Ctrl.fullPathName() ,
                                             shapeType=self.kCube, color=colors[1], width=2, height=2, depth=2,  character = rootNode, globalScale = True,
                                             constraint=self.kAim, aimVec=(0,0,1), upVec = (0,1,0) )

                eye_ctrl_grp_l = mc.listRelatives( Eyes_Lft_Ctrl.fullPathName(), p=True, pa=True )[0]
                eye_ctrl_grp_r = mc.listRelatives( Eyes_Rgt_Ctrl.fullPathName(), p=True, pa=True )[0]

                ty = mc.getAttr( eye_ctrl_grp + '.ty' )
                mc.setAttr( eye_ctrl_grp+ '.tz', ty/3 )

                # zero out the rotation on the right side
                mc.setAttr ( eye_ctrl_grp_r + '.rx', l=0 )
                mc.setAttr ( eye_ctrl_grp_r + '.ry', l=0 )
                mc.setAttr ( eye_ctrl_grp_r + '.rz', l=0 )
                mc.setAttr ( eye_ctrl_grp_r + '.r', 0,0,0 )
                mc.setAttr ( eye_ctrl_grp_r + '.rx', l=1 )
                mc.setAttr ( eye_ctrl_grp_r + '.ry', l=1 )
                mc.setAttr ( eye_ctrl_grp_r + '.rz', l=1 )

                mc.setAttr( eye_ctrl_grp + '.tx', l=1 )
                mc.setAttr( eye_ctrl_grp + '.tz', l=1 )

                # Space Switch
                self.create_space_switch( Eyes_Ctr_Ctrl, controls['Head_Ctr_Ctrl'], 'world', False )

            # Eyes
            #
            ######################################

            ##################################################################################################
            #
            # IKs
            iks = {}

            if self.DEBUG:
                print ('Create IK Legs')
            scale = mc.getAttr( rootNode + '.globalScale' )

            # Creates a constraint like transform calculation
            def matrix_multi(
                    name='matrix_multi',
                    inputs=['LegUpFK_Lft_Ctrl2', 'Hips_Ctr_Ctrl_LegUpFK_Lft_Ctrl2_Grp'],
                    inputs_inv=['LegUp_Lft_Jnt'],
                    inputs_inv_attr=['jointOrient'],
                    inputs_inv_comp_attr=['inputRotate']):

                name = self.short_name( name )
                mult = mc.createNode( 'multMatrix', name=name + '_multi', ss=True)
                decomp = mc.createNode( 'decomposeMatrix', name=name + '_decomp', ss=True)

                save_for_cleanup( mult )
                save_for_cleanup( decomp )

                mc.connectAttr( mult + '.matrixSum', decomp + '.inputMatrix' )

                for i in range(len(inputs)):
                    mc.connectAttr(inputs[i] + '.matrix', mult + '.matrixIn[{}]'.format(str(i + len(inputs_inv))))

                for i in range(len(inputs_inv)):
                    inv = mc.createNode('inverseMatrix', name=name + '_inv', ss=True)
                    comp = mc.createNode('composeMatrix', name=name + '_comp', ss=True)
                    for j in range(len(inputs_inv_attr)):
                        mc.connectAttr( inputs_inv[i].fullPathName() + '.' + inputs_inv_attr[j], comp + '.' + inputs_inv_comp_attr[j])

                    mc.connectAttr(comp + '.outputMatrix', inv + '.inputMatrix')
                    mc.connectAttr(inv + '.outputMatrix', mult + '.matrixIn[{}]'.format(str(i)))

                    save_for_cleanup(inv)
                    save_for_cleanup(comp)

                return decomp

            def hook_up_fk(joint, joint_ik, joint_fk, loc, name ):
                name = self.short_name( name )
                pb = mc.createNode('pairBlend', name=name + '_IK_' + SIDE + '_PB', ss=True)
                save_for_cleanup(pb)
                mc.setAttr(pb + '.rotInterpolation', 1)
                mc.connectAttr( loc.fullPathName() + '.' + ik_attr, pb + '.weight')

                # Use the global Scale to make the rig scalable
                mlt1 = mc.createNode('multiplyDivide', name=name + '_IK_' + SIDE + '_Multi1', ss=True)
                mlt2 = mc.createNode('multiplyDivide', name=name + '_IK_' + SIDE + '_Multi2', ss=True)
                save_for_cleanup(mlt1)
                save_for_cleanup(mlt2)
                mc.connectAttr( rootNode + '.globalScale', mlt1 + '.input1X' )
                mc.connectAttr( rootNode + '.globalScale', mlt1 + '.input1Y' )
                mc.connectAttr( rootNode + '.globalScale', mlt1 + '.input1Z' )

                # Neutralize global scale, non-one values will screw the rig, buggy if global scale is changed in control mode
                gs = mc.getAttr( rootNode + '.globalScale' )
                mc.setAttr( mlt1 + '.input2', 1/gs, 1/gs, 1/gs )

                mc.connectAttr( mlt1 + '.output', mlt2 + '.input1' )

                '''
                legUp_FK_decomp = matrix_multi(
                    name=name + '_FK_' + SIDE,
                    inputs=[
                        name + '_FK_' + SIDE + '_Ctrl',
                        name + '_FK_' + SIDE + '_Ctrl_Blnd_Grp',
                        name + '_FK_' + SIDE + '_Ctrl_Grp'
                    ],
                    inputs_inv=[
                        joints[ name + '_' + SIDE ]
                    ]
                )
                mc.connectAttr( legUp_FK_decomp + '.outputRotate', pb + '.inRotate1' )
                mc.connectAttr( legUp_FK_decomp + '.outputTranslate', pb + '.inTranslate1' )

                '''
                mc.connectAttr( joint_fk.fullPathName() + '.rotate', pb + '.inRotate1' )
                mc.connectAttr( joint_fk.fullPathName() + '.translate', pb + '.inTranslate1' )

                mc.connectAttr( joint_ik.fullPathName() + '.translate', pb + '.inTranslate2' )
                mc.connectAttr( joint_ik.fullPathName() + '.rotate', pb + '.inRotate2' )

                # Hook global scale here? We may need it pre PB
                mc.connectAttr(pb + '.outTranslate', mlt2 + '.input2')
                try:
                    mc.connectAttr(mlt2 + '.output', joint.fullPathName() + '.translate')
                    mc.connectAttr(pb + '.outRotate', joint.fullPathName() + '.rotate')
                except:
                    mc.warning("Can not connect to " + joint.fullPathName())
                    print( mc.listConnections( joint.fullPathName() + '.translate', s=1, d=0))
                return pb

            # Joints
            def joint_copy( jointToCopy, jointName, jointParent ):

                if not isinstance( jointToCopy, om.MDagPath ):
                    jointToCopy = self.get_path( jointToCopy )
                if not isinstance( jointParent, om.MDagPath ):
                    jointParent = self.get_path( jointParent )

                joint = mc.createNode('joint', parent=jointParent.fullPathName(), name=self.short_name( jointName ))
                joint = self.get_path( joint )

                mc.setAttr(
                    joint.fullPathName() + '.jo',
                    mc.getAttr(jointToCopy.fullPathName() + '.jo')[0][0],
                    mc.getAttr(jointToCopy.fullPathName() + '.jo')[0][1],
                    mc.getAttr(jointToCopy.fullPathName() + '.jo')[0][2]
                )
                mc.setAttr(
                    joint.fullPathName()  + '.pa',
                    mc.getAttr(jointToCopy.fullPathName() + '.pa')[0][0],
                    mc.getAttr(jointToCopy.fullPathName() + '.pa')[0][1],
                    mc.getAttr(jointToCopy.fullPathName() + '.pa')[0][2]
                )
                mc.matchTransform( joint.fullPathName(), jointToCopy.fullPathName() )
                return joint

            def joint_global_scale( joint ):
                joint_long = self.find_node( rootNode, joint )
                if joint is not None:
                    # Use the global Scale to make the rig scalable
                    mlt1 = mc.createNode('multiplyDivide', name=self.short_name( joint_long ) + '_GS_' + SIDE + '_Multi1', ss=True)
                    mlt2 = mc.createNode('multiplyDivide', name=self.short_name( joint_long ) + '_GS_' + SIDE + '_Multi2', ss=True)

                    save_for_cleanup(mlt1)
                    save_for_cleanup(mlt2)

                    mc.connectAttr(rootNode + '.globalScale', mlt1 + '.input1X')
                    mc.connectAttr(rootNode + '.globalScale', mlt1 + '.input1Y')
                    mc.connectAttr(rootNode + '.globalScale', mlt1 + '.input1Z')

                    # Neutralize global scale, non-one values will screw the rig
                    gs = mc.getAttr(rootNode + '.globalScale')
                    mc.setAttr(mlt1 + '.input2', 1 / gs, 1 / gs, 1 / gs)

                    mc.connectAttr( mlt1 + '.output', mlt2 + '.input1')

                    t = mc.getAttr( joint_long + '.t')[0]
                    mc.setAttr( mlt2 + '.input2', t[0], t[1], t[2])
                    mc.connectAttr(mlt2 + '.output', joint_long + '.translate', force=True )

            def createWorldOrient(node, root, value):
                # root = 'Main_Ctr_Ctrl'
                # node = 'ArmUp_FK_Lft_Ctrl'
                root = self.find_node( rootNode, root )

                node = self.find_node( rootNode, node )

                if node is None:
                    return None

                parent = mc.listRelatives(node, p=True, pa=True)[0]

                node_path = self.get_path( node )

                wo = mc.createNode( 'transform', name=self.short_name(node.replace('Ctrl', 'WorldOrient')), ss=True, parent=parent )

                mc.parent( node_path.fullPathName(), wo )


                orient = mc.orientConstraint( root, wo, mo=True)

                mc.addAttr(node_path.fullPathName(), ln='worldOrient', min=0, max=1)
                mc.setAttr(node_path.fullPathName() + '.worldOrient', k=True)

                target = mc.orientConstraint(orient, q=True, wal=True)[0]

                mc.connectAttr(node_path.fullPathName() + '.worldOrient', orient[0] + '.' + target)
                mc.setAttr(node_path.fullPathName() + '.worldOrient', value)


            ############################################################################################################
            # Sides

            for SIDE in ['Lft', 'Rgt']:

                ######################################################################
                # Leg

                hipsJnt  = joints[ 'Hips_Ctr' ]
                legUpJnt = joints[ 'LegUp_' + SIDE  ]
                legLoJnt = joints[ 'LegLo_' + SIDE  ]
                footJnt  = joints[ 'Foot_'  + SIDE  ]
                toesJnt  = joints[ 'Toes_'  + SIDE  ]
                hipsCtrl = controls['Hips_Ctr_Ctrl']

                ikName   = 'LegIKHandle_' + SIDE
                #poleVec  = 'LegPole_IK_' + SIDE + '_Ctrl'
                footLift = controls['FootLift_IK_' + SIDE + '_Ctrl']
                ik_attr  = 'FK_IK'

                side=sides[0]
                if SIDE == 'Rgt':
                    side=sides[1]

                blue = 1
                red = 0
                green = 0

                if SIDE == 'Rgt':
                    blue = 0
                    red = 1

                ########################################
                # IK
                # IK Loc
                ik_loc = mc.createNode('locator', parent=controls['LegUp_FK_' + SIDE + '_Ctrl'].fullPathName(), name='Leg_IK_' + SIDE)
                ik_loc = self.get_path( ik_loc )
                iks['Leg_IK_' + SIDE] = ik_loc
                mc.setAttr(ik_loc.fullPathName() + '.localScale', 0, 0, 0)
                mc.addAttr(ik_loc.fullPathName(), longName=ik_attr, min=0, max=1, at='float', defaultValue=1)
                mc.setAttr(ik_loc.fullPathName() + '.' + ik_attr, k=True)

                # Hide Attrs
                for attr in ['localScale', 'localPosition']:
                    for axis in ['X', 'Y', 'Z']:
                        mc.setAttr(ik_loc.fullPathName() + '.' + attr + axis, cb=False)

                for node in [ 'LegLo_FK_' + SIDE + '_Ctrl', 'Foot_FK_' + SIDE + '_Ctrl', 'Foot_IK_' + SIDE + '_Ctrl',
                             'FootLift_IK_' + SIDE + '_Ctrl', 'Toes_IK_' + SIDE + '_Ctrl',
                             'ToesTip_IK_' + SIDE + '_Ctrl', 'LegPole_IK_' + SIDE + '_Ctrl',
                             'Heel_IK_' + SIDE + '_Ctrl']:
                    if node in controls:
                        mc.parent( ik_loc.fullPathName(), controls[node].fullPathName(), add=True, shape=True)

                # IK Grp
                if self.DEBUG:
                    print ( 'IK Grp')
                ik_nul = mc.createNode('transform', name='legIK_' + SIDE + '_Grp', parent=hipsCtrl.fullPathName())
                mc.setAttr( ik_nul + '.v', 0 )
                mc.matchTransform(ik_nul, hipsJnt.fullPathName())

                if type == kBiped:
                    legUpJntIK_jnt_name = legUpJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )
                    legLoJntIK_jnt_name = legLoJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )
                    footJntIK_jnt_name  = footJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )
                    toesJntIK_jnt_name  = toesJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )

                elif type == kBipedUE:
                    legUpJntIK_jnt_name = legUpJnt.partialPathName().replace( '_' + side, '_IK_' + side )
                    legLoJntIK_jnt_name = legLoJnt.partialPathName().replace( '_' + side, '_IK_' + side )
                    footJntIK_jnt_name  = footJnt.partialPathName().replace( '_' + side, '_IK_' + side )
                    toesJntIK_jnt_name  = toesJnt.partialPathName().replace( '_' + side, '_IK_' + side )

                legUpJntIK = joint_copy( legUpJnt, legUpJntIK_jnt_name, ik_nul     )
                legLoJntIK = joint_copy( legLoJnt, legLoJntIK_jnt_name, legUpJntIK )
                footJntIK  = joint_copy( footJnt,  footJntIK_jnt_name,  legLoJntIK )
                toesJntIK  = joint_copy( toesJnt,  toesJntIK_jnt_name,  footJntIK  )

                mc.parentConstraint( controls['Toes_IK_{}_Ctrl'.format(SIDE)].fullPathName(), toesJntIK.fullPathName(), mo=True, skipTranslate=['x','y','z'] )

                ########################################################################################################
                #
                # Pole vector Position

                pole_matrix = self.get_polevector_position( legUpJntIK, legLoJntIK, footJntIK, leg_preferred_angle )

                parent = mc.listRelatives( controls[ 'LegPole_IK_' + SIDE + '_Ctrl' ].fullPathName(), p=True, pa=True )[ 0 ]
                parent = mc.listRelatives( parent, p = True, pa=True )[ 0 ]

                self.set_matrix( parent, pole_matrix, kWorld )

                for attr in [ 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz' ]:
                    mc.setAttr( parent + '.' + attr, l = True )

                # Pole vector Position
                #
                ########################################################################################################

                if type == kBiped:
                    hipsJntFK_jnt_name  = hipsJnt.partialPathName().replace( '_Jnt' , '_FK_Jnt' )
                    legUpJntFK_jnt_name = legUpJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                    legLoJntFK_jnt_name = legLoJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                    footJntFK_jnt_name  = footJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                    toesJntFK_jnt_name  = toesJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                elif type == kBipedUE:
                    # Proxy FK Joints
                    hipsJntFK_jnt_name  = hipsJnt.partialPathName() + '_FK'
                    legUpJntFK_jnt_name = legUpJnt.partialPathName().replace( '_' + side, '_FK_' + side )
                    legLoJntFK_jnt_name = legLoJnt.partialPathName().replace( '_' + side, '_FK_' + side )
                    footJntFK_jnt_name  = footJnt.partialPathName().replace( '_' + side, '_FK_' + side )
                    toesJntFK_jnt_name  = toesJnt.partialPathName().replace( '_' + side, '_FK_' + side )

                if SIDE == 'Lft':
                    hipsJntFK  = joint_copy( hipsJnt,  hipsJntFK_jnt_name,  prx_grp     )
                    save_for_cleanup( hipsJntFK.fullPathName() )

                legUpJntFK = joint_copy( legUpJnt, legUpJntFK_jnt_name, hipsJntFK   )
                legLoJntFK = joint_copy( legLoJnt, legLoJntFK_jnt_name, legUpJntFK  )
                footJntFK  = joint_copy( footJnt,  footJntFK_jnt_name,  legLoJntFK  )
                toesJntFK  = joint_copy( toesJnt,  toesJntFK_jnt_name,  footJntFK   )

                mc.parentConstraint( controls['Hips_Ctr_Ctrl'].fullPathName(),          hipsJntFK.fullPathName(),  mo=True )
                mc.parentConstraint( controls['LegUp_FK_'+SIDE+'_Ctrl'].fullPathName(), legUpJntFK.fullPathName(), mo=True )
                mc.parentConstraint( controls['LegLo_FK_'+SIDE+'_Ctrl'].fullPathName(), legLoJntFK.fullPathName(), mo=True )
                mc.parentConstraint( controls['Foot_FK_'+SIDE+'_Ctrl'].fullPathName(),  footJntFK.fullPathName(),  mo=True )
                mc.parentConstraint( controls['Toes_FK_'+SIDE+'_Ctrl'].fullPathName(),  toesJntFK.fullPathName(),  mo=True )

                # Visibility based on IK/FK mode
                rev = mc.createNode( 'reverse', name=self.short_name( ik_loc.partialPathName() ) +'_rev', ss=True  )
                mc.connectAttr( ik_loc.fullPathName() + '.' + ik_attr, rev + '.inputX')

                for ctl in [ 'LegUp_FK_' + SIDE + '_Ctrl', 'LegLo_FK_' + SIDE + '_Ctrl', 'Foot_FK_' + SIDE + '_Ctrl', 'Toes_FK_' + SIDE + '_Ctrl' ]:
                    mc.connectAttr( rev + '.outputX', controls[ctl].fullPathName() + '.v')

                for ctl in [ 'Foot_IK_' + SIDE + '_Ctrl', 'FootLift_IK_' + SIDE + '_Ctrl', 'Heel_IK_' + SIDE + '_Ctrl', 'Toes_IK_' + SIDE + '_Ctrl', 'ToesTip_IK_' + SIDE + '_Ctrl' ]:
                    mc.connectAttr( ik_loc.fullPathName() + '.' + ik_attr, controls[ctl].fullPathName() + '.v')


                # IK Handle
                mc.orientConstraint( controls['FootLift_IK_'+SIDE+'_Ctrl'].fullPathName(), footJntIK, mo=True)
                mc.setAttr( legLoJntIK.fullPathName() + '.preferredAngle',leg_preferred_angle[0], leg_preferred_angle[1], leg_preferred_angle[2] )
                ik = mc.ikHandle(n=ikName, sj=legUpJntIK.fullPathName(), ee=footJntIK.fullPathName() )


                ikHandle = '|'+ik[0]
                effector = ik[1]
                mc.poleVectorConstraint( controls['LegPole_IK_'+SIDE+'_Ctrl'].fullPathName(), ikHandle )
                mc.setAttr(ikHandle + '.v', 0)
                mc.setAttr(ikHandle + '.snapEnable', False)
                mc.setAttr(ikHandle + '.stickiness', True)

                mc.parent( ikHandle, controls['FootLift_IK_'+SIDE+'_Ctrl'].fullPathName() )

                # IK
                ########################################

                hook_up_fk( legUpJnt, legUpJntIK, legUpJntFK, ik_loc,  'LegUp' )
                hook_up_fk( legLoJnt, legLoJntIK, legLoJntFK, ik_loc,  'LegLo' )
                hook_up_fk( footJnt,  footJntIK,  footJntFK,  ik_loc,  'Foot'  )
                hook_up_fk( toesJnt,  toesJntIK,  toesJntFK,  ik_loc,  'Toes'  )

                joint_global_scale( self.find_node( rootNode, 'Heel_'+SIDE+'_Jnt'    ))
                joint_global_scale( self.find_node( rootNode, 'ToesTip_'+SIDE+'_Jnt' ))
                joint_global_scale( self.find_node( rootNode, 'Eye_'+SIDE+'_Jnt'     ))

                if SIDE == 'Lft':
                    joint_global_scale( self.find_node( rootNode, 'Head_Jnt_Tip' ))
                    joint_global_scale( self.find_node( rootNode, 'Jaw_Jnt'      ))
                    joint_global_scale( self.find_node( rootNode, 'Jaw_Jnt_Tip'  ))

                mc.setAttr (  ik_loc.fullPathName() + '.FK_IK', 1)

                # Space Switch

                feet_iks = [ controls[ 'Foot_IK_'+SIDE+'_Ctrl' ] ]

                root_path = self.get_path(rootNode)

                for node in feet_iks:
                    self.create_multi_space_switch(
                        node,
                        [ controls[ 'Main_Ctr_Ctrl'], controls[ 'Hips_Ctr_Ctrl'], controls[ 'Torso_Ctr_Ctrl'], root_path ],
                        attrName='space',
                        attrNameList=['Main', 'Hips', 'Torso', 'World']
                    )

                # Leg
                ######################################################################

                ######################################################################
                # Arm

                clavJnt     = joints[ 'Clavicle_' + SIDE  ]
                armUpJnt    = joints[ 'ArmUp_' + SIDE  ]
                armLoJnt    = joints[ 'ArmLo_' + SIDE  ]
                handJnt     = joints[ 'Hand_'  + SIDE  ]
                main        = controls['Main_Ctr_Ctrl' ]
                poleVec     = controls['ArmPole_IK_' + SIDE + '_Ctrl']
                ikName      = 'ArmIKHandle_' + SIDE

                # Clavicle
                mc.parentConstraint( controls['Clavicle_'+SIDE+'_Ctrl'].fullPathName(), clavJnt, mo=True  )

                # IK Loc
                ik_loc = mc.createNode('locator', parent=controls['ArmUp_FK_'+SIDE+'_Ctrl'].fullPathName(), name='Arm_IK_' + SIDE)
                ik_loc = self.get_path( ik_loc )
                iks['Arm_IK_' + SIDE] = ik_loc
                mc.setAttr(ik_loc.fullPathName() + '.localScale', 0, 0, 0)
                mc.addAttr(ik_loc.fullPathName(), longName=ik_attr, min=0, max=1, at='float', defaultValue=0)
                mc.setAttr(ik_loc.fullPathName() + '.' + ik_attr, k=True)

                # Hide Attrs
                for attr in ['localScale', 'localPosition']:
                    for axis in ['X', 'Y', 'Z']:
                        mc.setAttr(ik_loc.fullPathName() + '.' + attr + axis, cb=False)

                # Parent IK Shape under Ctrl transforms for easy access
                for node in [ 'ArmLo_FK_' + SIDE + '_Ctrl',
                              'Hand_FK_' + SIDE + '_Ctrl',
                              'ArmPole_IK_' + SIDE + '_Ctrl',
                              'Hand_IK_' + SIDE + '_Ctrl' ]:
                    mc.parent(ik_loc.fullPathName(), controls[node].fullPathName(), add=True, shape=True)

                clav = controls['Clavicle_'+SIDE+'_Ctrl']

                # Proxy FK Joints
                if type == kBiped:
                    clavJntIK_jnt_name  = clavJnt.partialPathName().replace(  '_' + SIDE, '_FK_' + SIDE )
                    armUpJntIK_jnt_name = armUpJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                    armLoJntIK_jnt_name = armLoJnt.partialPathName().replace( '_' + SIDE, '_FK_' + SIDE )
                    handJntIK_jnt_name  = handJnt.partialPathName().replace(  '_' + SIDE, '_FK_' + SIDE )

                    armUpJntIK_jnt_name = armUpJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )
                    armLoJntIK_jnt_name = armLoJnt.partialPathName().replace( '_' + SIDE, '_IK_' + SIDE )
                    handJntIK_jnt_name  = handJnt.partialPathName().replace(  '_' + SIDE, '_IK_' + SIDE )

                elif type == kBipedUE:
                    clavJntFK_jnt_name  = clavJnt.partialPathName().replace(  '_' + side, '_FK_' + side )
                    armUpJntFK_jnt_name = armUpJnt.partialPathName().replace( '_' + side, '_FK_' + side )
                    armLoJntFK_jnt_name = armLoJnt.partialPathName().replace( '_' + side, '_FK_' + side )
                    handJntFK_jnt_name  = handJnt.partialPathName().replace(  '_' + side, '_FK_' + side )

                    clavJntIK_jnt_name  = clavJnt.partialPathName().replace(  '_' + side, '_IK_' + side )
                    armUpJntIK_jnt_name = armUpJnt.partialPathName().replace( '_' + side, '_IK_' + side )
                    armLoJntIK_jnt_name = armLoJnt.partialPathName().replace( '_' + side, '_IK_' + side )
                    handJntIK_jnt_name  = handJnt.partialPathName().replace(  '_' + side, '_IK_' + side )

                arm_grp = mc.createNode('transform', name='arms_'+SIDE+'_grp', parent=prx_grp, ss=True)
                mc.setAttr( arm_grp + '.v', False )
                save_for_cleanup( arm_grp )

                clavJntFK  = joint_copy( clavJnt,  clavJntFK_jnt_name, arm_grp       )
                armUpJntFK = joint_copy( armUpJnt, armUpJntFK_jnt_name, clavJntFK   )
                armLoJntFK = joint_copy( armLoJnt, armLoJntFK_jnt_name, armUpJntFK  )
                handJntFK  = joint_copy( handJnt,  handJntFK_jnt_name,  armLoJntFK   )

                armUpJntIK = joint_copy( armUpJnt, armUpJntIK_jnt_name, clavJntFK         )
                armLoJntIK = joint_copy( armLoJnt, armLoJntIK_jnt_name, armUpJntIK   )
                handJntIK  = joint_copy( handJnt,  handJntIK_jnt_name, armLoJntIK    )

                mc.parentConstraint( controls['Clavicle_'+SIDE+'_Ctrl'].fullPathName(), clavJntFK.fullPathName(), mo=True  )
                mc.parentConstraint( controls['ArmUp_FK_'+SIDE+'_Ctrl'].fullPathName(), armUpJntFK.fullPathName(), mo=True )
                mc.parentConstraint( controls['ArmLo_FK_'+SIDE+'_Ctrl'].fullPathName(), armLoJntFK.fullPathName(), mo=True )
                mc.parentConstraint( controls['Hand_FK_'+SIDE+'_Ctrl'].fullPathName(), handJntFK.fullPathName(), mo=True )

                # IK Handle
                mc.setAttr( armLoJntIK.fullPathName()  + '.preferredAngle', 0, 0, -45)
                ik = mc.ikHandle(n=ikName, sj=armUpJntIK.fullPathName() , ee=handJntIK.fullPathName() , solver ='ikRPsolver' )

                # It seems that the ikHandle command does not yield a unique DAG path
                ikHandle = '|'+ik[0]
                effector = ik[1]
                mc.poleVectorConstraint(  poleVec.fullPathName(), ikHandle )
                mc.setAttr(ikHandle + '.v', 0)
                mc.setAttr(ikHandle + '.stickiness', True)
                mc.setAttr(ikHandle + '.snapEnable', False)
                mc.parent(ikHandle, controls['Hand_IK_'+SIDE+'_Ctrl'].fullPathName() )
                #mc.orientConstraint('FootLift_IK_' + SIDE + '_Ctrl', footJntIK, mo=True)

                hook_up_fk( armUpJnt, armUpJntIK,  armUpJntFK, ik_loc,  'ArmUp' )
                hook_up_fk( armLoJnt, armLoJntIK,  armLoJntFK, ik_loc,  'ArmLo' )


                ########################################################################################################
                #
                # Pole vector Position

                pole_matrix = self.get_polevector_position( armUpJntIK, armLoJntIK, handJntIK, arm_preferred_angle )

                parent = mc.listRelatives( controls[ 'ArmPole_IK_' + SIDE + '_Ctrl' ].fullPathName(), p=True, pa=True )[ 0 ]
                parent = mc.listRelatives( parent, p=True, pa=True )[ 0 ]

                self.set_matrix( parent, pole_matrix, kWorld )

                for attr in [ 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz' ]:
                    mc.setAttr( parent + '.' + attr, l = True )

                # Pole vector Position
                #
                ########################################################################################################


                # Create Switch to orient the hand to the IK Ctrl
                hand_ctrl =  self.find_node(rootNode, 'Hand_FK_'+SIDE+'_Ctrl')
                hand_parent = mc.listRelatives( hand_ctrl, p=True, pa=True )[0]
                hand_parent = mc.listRelatives( hand_parent, p=True, pa=True )[0]

                # Make the Hand follow the arm joint for IK/FK Blending
                for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
                    mc.setAttr( hand_parent + '.' + attr, l=False)


                cnst = mc.parentConstraint(
                    armLoJnt,
                    controls['Hand_IK_'+SIDE+'_Ctrl'].fullPathName(),
                    hand_parent,
                    mo=True
                )
                # Avoids flipping
                mc.setAttr( cnst[0] + '.interpType', 2)

                alias = mc.parentConstraint( cnst[0], q=True, wal=True )

                mc.addAttr( ik_loc.fullPathName(), longName='lockHandRot', min=0, max=1, dv=0 )
                mc.setAttr( ik_loc.fullPathName()+ '.lockHandRot', k=True )

                mc.connectAttr( ik_loc.fullPathName()+ '.lockHandRot', cnst[0] + '.' + alias[1] )

                rev = mc.createNode('reverse', ss=True, name=self.short_name( controls['Hand_IK_'+SIDE+'_Ctrl'].fullPathName() )+'_Lock_Rev')
                mc.connectAttr( ik_loc.fullPathName() + '.lockHandRot', rev + '.inputX' )
                mc.connectAttr( rev + '.outputX', cnst[0] + '.' + alias[0] )

                mc.parent( hand_parent, controls['Main_Ctr_Ctrl'] )

                hand_space_ctrls = []

                for node in hand_space_switch_list:
                    hand_space_ctrls.append( controls[node] )

                root_path = self.get_path(rootNode)

                # Space Switch
                for node in [ controls['Hand_IK_'+SIDE+'_Ctrl'], controls['ArmPole_IK_'+SIDE+'_Ctrl'], root_path ]:
                    self.create_multi_space_switch(
                        node,
                        hand_space_ctrls,
                        attrName='space',
                        attrNameList=['Main', 'Head', 'Chest', 'Hips', 'Torso', 'World']
                    )
                # Hide the attribute on the pole Vector
                #ArmPoleVecIK_Ctrl[0] = self.find_node( rootNode, ArmPoleVecIK_Ctrl[0] )
                mc.setAttr ( controls['ArmPole_IK_'+SIDE+'_Ctrl'].fullPathName() + '.space', k=False )

                # Connect the Hand Ik to the PoleVec space to have matching spaces
                #HandIK_Ctrl[0] = self.find_node( rootNode, HandIK_Ctrl[0] )
                mc.connectAttr(
                    controls['Hand_IK_'+SIDE+'_Ctrl'].fullPathName() + '.space',
                    controls['ArmPole_IK_'+SIDE+'_Ctrl'].fullPathName() + '.space'
                )

                # Visibility based on IK/FK mode
                rev = mc.createNode( 'reverse', name=self.short_name( ik_loc.fullPathName() )+'_rev', ss=True  )
                mc.connectAttr( ik_loc.fullPathName() + '.' + ik_attr, rev + '.inputX')

                for node in [
                    controls['ArmUp_FK_' + SIDE + '_Ctrl'],
                    controls['ArmLo_FK_' + SIDE + '_Ctrl']
                ]:
                    node = mc.listRelatives( node.fullPathName(), p=True, pa=True )[0]
                    mc.setAttr( node + '.v', l=False )
                    mc.connectAttr( rev + '.outputX', node + '.v')

                for node in [ controls['Hand_IK_'+SIDE+'_Ctrl'], controls['ArmPole_IK_'+SIDE+'_Ctrl']]:
                    mc.setAttr( node.fullPathName() + '.v', l=False )
                    mc.connectAttr(  ik_loc.fullPathName() + '.' + ik_attr, node.fullPathName() + '.v' )

                # Arm
                ######################################################################

            #######################################################################
            #
            # World Orient
            if self.DEBUG:
                print ('Create Orients')

            for SIDE in ['Lft', 'Rgt']:
                armUp = self.find_node( rootNode, 'ArmUp_FK_' + SIDE + '_Ctrl' )
                createWorldOrient( armUp, controls['Main_Ctr_Ctrl'], 1)

            createWorldOrient( controls['Head_Ctr_Ctrl'], controls['Main_Ctr_Ctrl'], 1)


            for node in ['Spine1_Ctr_Ctrl', 'Spine2_Ctr_Ctrl', 'Spine3_Ctr_Ctrl', 'Chest_Ctr_Ctrl']:
                node = self.find_node( rootNode, node )
                createWorldOrient( node, controls['Main_Ctr_Ctrl'], 0 )

            # World Orient
            #
            #######################################################################
            #
            # Meta Data
            if self.DEBUG:
                print ('Create Meta Data')

            def set_data ( handles, data ):

                for handle in handles:
                    self.set_metaData(handle, data)

            for SIDE in ['Lft', 'Rgt']:

                data = {}
                data['Type'] = kHandle

                if SIDE == 'Rgt':
                    data['Side'] = kRight
                else:
                    data['Side'] = kLeft

                handles = [ iks['Arm_IK_'+SIDE], iks['Leg_IK_'+SIDE] ]

                set_data( handles, data )

                data['Mirror'] = kSymmetricRotation

                handles = []

                for ctl in controls.keys():
                    if SIDE in ctl:
                        handles.append( controls[ctl] )

                set_data(  handles, data )

                handles = [
                    controls['LegPole_IK_'+SIDE+'_Ctrl'],
                    controls['ShoulderUpVec_'+SIDE+'_Ctrl'],
                    controls['Hand_IK_'+SIDE+'_Ctrl'],
                    controls['ArmPole_IK_'+SIDE+'_Ctrl'],
                    controls['HipsUpVec_'+SIDE+'_Ctrl']
                ]

                set_data(  handles, data )

                data['Mirror'] = kBasic
                data['Limb'] = 'Leg'
                data['Kinematic'] = 'IK'
                handles_ik = [controls['Foot_IK_'+SIDE+'_Ctrl'], controls['LegPole_IK_'+SIDE+'_Ctrl'] ]
                set_data(  handles_ik, data )

                data['Mirror'] = kSymmetricRotation
                handles_ik = [controls['FootLift_IK_'+SIDE+'_Ctrl'],  controls['Toes_IK_'+SIDE+'_Ctrl'], controls['ToesTip_IK_'+SIDE+'_Ctrl'], controls['Heel_IK_'+SIDE+'_Ctrl'] ]

                set_data(  handles_ik, data )

                data['Kinematic'] = 'FK'
                handles_fk = [controls['LegUp_FK_'+SIDE+'_Ctrl'], controls['LegLo_FK_'+SIDE+'_Ctrl'], controls['Foot_FK_'+SIDE+'_Ctrl'], controls['Toes_FK_'+SIDE+'_Ctrl'] ]

                set_data( handles_fk, data )

            data['Side'] = kCenter
            data['Mirror'] = kBasic

            handles_Ctr = []
            for ctl in controls.keys():
                if '_Ctr_' in ctl:
                    handles_Ctr.append( controls[ctl] )

            set_data(  handles_Ctr, data )

            # Main Root
            data = {}
            data['Type'] = kMain
            data['Side'] = kCenter

            self.set_metaData( controls['Main_Ctr_Ctrl'], data)

            # Meta Data
            #
            ##################################################################################################

            if self.DEBUG:
                print( 'Recreate custom controls')

            # Recreate the custom Controls
            if len(self.rigCustomCtrls):
                self.create_custom_control( **self.rigCustomCtrls )

            data = {}
            data['Type'] = kHandle
            handles = self.get_nodes( main, data)
            handles = sorted(handles)

            attrs = ['visibility']

            for handle in handles:
                handle = self.find_node( rootNode, handle )
                for attr in attrs:
                    mc.setAttr(handle + '.' + attr, l=True, k=False, cb=False)

            #charName = 'Adam'
            data = {}
            data['Type'] = kMain
            nodes = self.get_nodes(main, data)

            if 'ControlShapeData' in rootData:

                ctrlData = rootData['ControlShapeData']
                for node in ctrlData.keys():
                    actual_node = self.find_node( rootNode, node )
                    if len ( ctrlData[node]) > 0:
                        for attr in ctrlData[node].keys():
                            try:
                                mc.setAttr( actual_node + '.' + attr, ctrlData[node][attr])
                            except:
                                pass

            if self.DEBUG:
                print( 'Visbility switches')
            mc.select(cl=True)

            dict = {}
            dict['Arms'] = ['Clavicle_Lft_Ctrl', 'ArmUp_FK_Lft_Ctrl', 'ArmLo_FK_Lft_Ctrl', 'Hand_FK_Lft_Ctrl' ]
            dict['Finger'] = ['Index1_Lft_Ctrl', 'Index2_Lft_Ctrl', 'Index3_Lft_Ctrl', 'Index4_Lft_Ctrl',
                                'Middle1_Lft_Ctrl', 'Middle2_Lft_Ctrl', 'Middle3_Lft_Ctrl', 'Middle4_Lft_Ctrl',
                                'Ring1_Lft_Ctrl', 'Ring2_Lft_Ctrl', 'Ring3_Lft_Ctrl', 'Ring4_Lft_Ctrl',
                                'Pinky1_Lft_Ctrl', 'Pinky2_Lft_Ctrl', 'Pinky3_Lft_Ctrl', 'Pinky4_Lft_Ctrl',
                                'Thumb1_Lft_Ctrl', 'Thumb2_Lft_Ctrl', 'Thumb3_Lft_Ctrl' ]

            dict['Legs'] = ['Foot_IK_Lft_Ctrl_Grp', 'LegUp_FK_Lft_Ctrl_Grp' ]
            dict['Head'] = ['Head_Ctr_Ctrl', 'Neck_Ctr_Ctrl']
            dict['Torso'] = ['Torso_Ctr_Ctrl', 'Hips_Ctr_Ctrl', 'Spine1_Ctr_Ctrl', 'Spine2_Ctr_Ctrl', 'Spine3_Ctr_Ctrl',
                               'Chest_Ctr_Ctrl']
            dict['UpVectors'] = [ 'ShoulderUpVec_Lft_Ctrl', 'HipsUpVec_Lft_Ctrl' ]

            # Connect the visibility
            visNode = rootNode
            for key in dict.keys():
                attrName = 'show_'+key
                if not mc.attributeQuery( 'show_'+key, node=visNode, exists=True):
                    mc.addAttr( visNode, longName=attrName, enumName='off:on', defaultValue=1, at='enum' )
                    mc.setAttr(visNode+'.' + attrName, k=True)
                for node in dict[key]:
                    try:
                        node = self.find_node( rootNode, node )
                        mc.setAttr( node + '.v', lock=False )
                        mc.connectAttr( visNode + '.' + attrName, node + '.v', force=True )

                        if 'Lft' in node:
                            rgtNode = node.replace('Lft', 'Rgt')
                            rgtNode = self.find_node( rootNode, rgtNode )
                            if mc.objExists(rgtNode):
                                mc.setAttr( rgtNode + '.v', lock=False )
                                mc.connectAttr( visNode + '.' + attrName, rgtNode + '.v', force=True )
                    except:
                        pass

            # Hide Up Vectors per default
            mc.setAttr( visNode + '.show_UpVectors', False )

            if self.DEBUG:
                print( 'Lock attributes')
            # Lock Attrs
            nodes = ['ToesTip_IK_Lft_Ctrl',
                     'Heel_IK_Lft_Ctrl',
                     'Toes_IK_Lft_Ctrl',
                     'FootLift_IK_Lft_Ctrl',
                     'Hips_Ctr_Ctrl',
                     'Spine1_Ctr_Ctrl',
                     'Spine2_Ctr_Ctrl',
                     'Spine3_Ctr_Ctrl',
                      'Chest_Ctr_Ctrl'
                     ]
            nodes.extend( dict['Arms'] )
            nodes.extend( dict['Finger'] )
            nodes.extend( dict['Head'] )

            nodes = ['LegPole_IK_Lft_Ctrl', 'ShoulderUpVec_Lft_Ctrl', 'HipsUpVec_Lft_Ctrl',
                     'ArmPole_IK_Lft_Ctrl']

            if self.DEBUG:
                print( 'Lock attributes IKs and UpVecs')

            for node in nodes:
                node = controls[node].fullPathName()

                if node is not None:
                    for attr in ['rx','ry','rz','sx','sy','sz']:
                        if mc.objExists( node ):
                            try:
                                mc.setAttr( node + '.' + attr, l=True, k=False )
                            except:
                                pass
                        rgtNode = node.replace('Lft', 'Rgt')
                        rgtNode = self.find_node( rootNode, rgtNode )
                        if mc.objExists(rgtNode):
                            try:
                                mc.setAttr( rgtNode + '.' + attr, l=True, k=False)
                            except:
                                pass
                else:
                    mc.warning( 'aniMeta: Can not find node ' + str( node ) )

            #handles_Lft = self.get_nodes(rootNode, {'Side': kLeft, 'Type': kHandle }, hierarchy=True)
            handles_Lft = []

            for node in controls.keys():
                if 'Lft' in node:
                    handles_Lft.append( node )

            if self.DEBUG:
                print ( 'Connect Control Sizes')

            for i in range(len(handles_Lft)):

                lft = controls[ handles_Lft[i] ].fullPathName()
                rgt = handles_Lft[i].replace('Lft', 'Rgt')
                rgt = controls[ rgt ].fullPathName()

                if mc.objExists(rgt):

                    try:
                        mc.connectAttr(lft + '.controlSize', rgt + '.controlSize')
                    except:
                        pass
                    try:
                        mc.connectAttr(lft + '.controlSizeX', rgt + '.controlSizeX')
                        mc.connectAttr(lft + '.controlSizeY', rgt + '.controlSizeY')
                        mc.connectAttr(lft + '.controlSizeZ', rgt + '.controlSizeZ')
                    except:
                        pass

                    data = self.get_metaData( lft )

                    if 'Mirror' in data:

                        x,y,z = 1,1,1

                        if data['Mirror'] == kSymmetricRotation:
                            x,y,z = 1, -1, -1

                        if data['Mirror'] == kBasic:
                            x = -1

                        try:
                            rev = mc.createNode('multiplyDivide', name=self.short_name( rgt ) + '_controlOffset_inv', ss=True)
                            mc.setAttr(rev + '.input2', x, y, z )
                            mc.connectAttr(lft + '.controlOffset', rev + '.input1')
                            mc.connectAttr(rev + '.output', rgt + '.controlOffset')
                        except:
                            pass
                else:
                    mc.warning('aniMeta: invalid right handle', rgt)

            #self.build_pickwalking( rootNode )

    def switch_fkik(self, **kwargs):

        am = AniMeta()
        char = None
        limb = None
        side = None
        newMode = 0

        type = self.get_char_type()

        if 'Character' in kwargs:
            char = kwargs['Character']

        if 'Limb' in kwargs:
            limb = kwargs['Limb']
        if 'Side' in kwargs:
            side = kwargs['Side']

        side_UE = 'l'
        if side == 'Rgt':
            side_UE = 'r'

        # TODO: Make sure rig is in control mode

        if char and limb and side:

            ctrl = 'Foot_IK_Lft_Ctrl'

            if limb == 'Leg' and side == 'Lft':
                ctrl = 'Foot_IK_Lft_Ctrl'

            if limb == 'Leg' and side == 'Rgt':
                ctrl = 'Foot_IK_Rgt_Ctrl'

            if limb == 'Arm' and side == 'Rgt':
                ctrl = 'Hand_IK_Rgt_Ctrl'

            if limb == 'Arm' and side == 'Lft':
                ctrl = 'Hand_IK_Lft_Ctrl'

            ik_node = self.find_node( char, ctrl )

            newMode = 1 - int(mc.getAttr(ik_node + '.FK_IK'))

            ############################################################################################################
            # Leg

            if limb == 'Leg':

                # From IK to FK
                if newMode == 0:

                    nodes  = ['LegUp_FK_{}_Ctrl', 'LegLo_FK_{}_Ctrl', 'Foot_FK_{}_Ctrl', 'Toes_FK_{}_Ctrl']

                    if type == kBiped:
                        joints = ['LegUp_IK_{}_Jnt', 'LegLo_IK_{}_Jnt', 'Foot_IK_{}_Jnt', 'Toes_IK_{}_Jnt']
                    elif type == kBipedUE:
                        joints = ['thigh_IK_{}', 'calf_IK_{}', 'foot_IK_{}', 'ball_IK_{}']

                    for i in range(len(nodes)):
                        ctrlName = nodes[i].format(side)
                        jntName  = joints[i].format(side)
                        if type == kBipedUE:
                            jntName  = joints[i].format(side_UE)

                        ctrl     = am.find_node(char, ctrlName)
                        jnt      = am.find_node(char, jntName)

                        if ctrl is None:
                            mc.warning('aniMeta: can not find ' + ctrlName)
                            break
                        if jnt is None:
                            mc.warning('aniMeta: can not find ' + jntName)
                            break

                        m = self.get_matrix( jnt, kWorld )
                        self.set_matrix(ctrl, m, kWorld, setScale=False )

                    mc.setAttr(ik_node + '.FK_IK', 0)

                # From FK to IK
                elif newMode == 1:

                    # Heel
                    heel_ctrl     = 'Heel_IK_{}_Ctrl'.format(side)
                    toesTip_ctrl  = 'ToesTip_IK_{}_Ctrl'.format(side)
                    footLift_ctrl = 'FootLift_IK_{}_Ctrl'.format(side)

                    for node in [heel_ctrl, toesTip_ctrl, footLift_ctrl]:
                        node = am.find_node(char, node)
                        if node:
                            self.reset_handle( node )

                    pole_ik      = 'LegPole_IK_{}_Ctrl'.format(side)
                    foot_ik      = 'Foot_IK_{}_Ctrl'.format(side)
                    # Foot
                    if type == kBiped:
                        legUp_ik_jnt = 'LegUp_IK_{}_Jnt'.format(side)
                        legLo_ik_jnt = 'LegLo_IK_{}_Jnt'.format(side)
                        foot_jnt     = 'Foot_{}_Jnt'.format(side)
                    elif type == kBipedUE:
                        legUp_ik_jnt = 'thigh_IK_{}'.format(side_UE)
                        legLo_ik_jnt = 'calf_IK_{}'.format(side_UE)
                        foot_jnt     = 'foot_IK_{}'.format(side_UE)

                    legUp_ik_jnt = am.find_node(char, legUp_ik_jnt)
                    legLo_ik_jnt = am.find_node(char, legLo_ik_jnt)
                    pole_ik      = am.find_node(char, pole_ik)
                    foot_ik      = am.find_node(char, foot_ik)
                    foot_jnt     = am.find_node(char, foot_jnt)

                    m = self.get_matrix( foot_jnt, kWorld )

                    if side == 'Rgt':
                        m = om.MEulerRotation( math.radians(180),0,0 ).asMatrix() * m

                    self.set_matrix(foot_ik, m, kWorld, setScale = False )

                    pa = mc.getAttr( legLo_ik_jnt + '.preferredAngle' )[0]

                    out = self.get_polevector_position( legUp_ik_jnt, legLo_ik_jnt, foot_jnt, pa )

                    self.set_matrix( pole_ik, out, kWorld)

                    mc.setAttr(ik_node + '.FK_IK', 1)

            # Leg
            ############################################################################################################


            ############################################################################################################
            # Arm

            if limb == 'Arm':

                # From IK to FK
                if newMode == 0:

                    nodes  = ['ArmUp_FK_{}_Ctrl', 'ArmLo_FK_{}_Ctrl', 'Hand_FK_{}_Ctrl' ]
                    if type == kBiped:
                        joints = ['ArmUp_{}_Jnt', 'ArmLo_{}_Jnt', 'Hand_{}_Jnt' ]
                    elif type == kBipedUE:
                        joints = ['upperarm_{}', 'lowerarm_{}', 'hand_{}' ]

                    for i in range(len(nodes)):
                        ctrlName = nodes[i].format(side)
                        jntName  = joints[i].format(side)
                        if type == kBipedUE:
                            jntName  = joints[i].format(side_UE)
                        ctrl     = am.find_node(char, ctrlName)
                        jnt      = am.find_node(char, jntName)

                        if ctrl is None:
                            mc.warning('aniMeta: can not find ', ctrlName)
                            break
                        if jnt is None:
                            mc.warning('aniMeta: can not find ', jntName)
                            break

                        m = self.get_matrix( jnt )
                        self.set_matrix( ctrl, m )

                    mc.setAttr(ik_node + '.FK_IK', 0)

                # From FK to IK
                elif newMode == 1:

                    pole_ik      = 'ArmPole_IK_{}_Ctrl'.format(side)
                    hand_ik      = 'Hand_IK_{}_Ctrl'.format(side)

                    # Foot
                    if type == kBiped:
                        armUp_ik_jnt = 'ArmUp_IK_{}_Jnt'.format(side)
                        armLo_ik_jnt = 'ArmLo_IK_{}_Jnt'.format(side)
                        hand_jnt     = 'Hand_{}_Jnt'.format(side)
                    elif type == kBipedUE:
                        armUp_ik_jnt = 'upperarm_IK_{}'.format(side_UE)
                        armLo_ik_jnt = 'lowerarm_IK_{}'.format(side_UE)
                        hand_jnt     = 'hand_{}'.format(side_UE)

                    armUp_ik_jnt = am.find_node(char, armUp_ik_jnt)
                    armLo_ik_jnt = am.find_node(char, armLo_ik_jnt)
                    pole_ik      = am.find_node(char, pole_ik)
                    hand_ik      = am.find_node(char, hand_ik)
                    hand_jnt     = am.find_node(char, hand_jnt)

                    m = self.get_matrix(hand_jnt)

                    if side == 'Rgt':
                        m = om.MEulerRotation(math.radians(180),0,0).asMatrix() * m

                    self.set_matrix(hand_ik, m, setScale = False )

                    pa = mc.getAttr( armLo_ik_jnt + '.preferredAngle' )[0]
                    out = Transform().get_polevector_position( armUp_ik_jnt, armLo_ik_jnt, hand_jnt, pa )

                    Transform().set_matrix( pole_ik, out, kWorld)

                    mc.setAttr(ik_node + '.FK_IK', 1)

            # Arm
            ############################################################################################################


        else:
            mc.warning('aniMeta: can not switch rig ', char, limb, side)
        return newMode

    def build_pickwalking(self, char ):

        # Deactivated for now
        return True

        def parent_controller(  node1, node2 ):
            node1 = self.find_node(char, node1)
            node2 = self.find_node(char, node2)
            if node1 is not None and node2 is not None:
                mc.controller( node1, node2, parent=True)

        mc.controller( self.find_node(char, 'Main_Ctr_Ctrl'))
        parent_controller( 'Torso_Ctr_Ctrl',    'Main_Ctr_Ctrl' )
        parent_controller( 'Hips_Ctr_Ctrl',     'Torso_Ctr_Ctrl' )
        parent_controller( 'Spine1_Ctr_Ctrl',   'Hips_Ctr_Ctrl' )
        parent_controller( 'Spine2_Ctr_Ctrl',   'Spine1_Ctr_Ctrl' )
        parent_controller( 'Spine3_Ctr_Ctrl',   'Spine2_Ctr_Ctrl' )
        parent_controller( 'Chest_Ctr_Ctrl',    'Spine3_Ctr_Ctrl' )
        parent_controller( 'Neck_Ctr_Ctrl',     'Chest_Ctr_Ctrl' )
        parent_controller( 'Head_Ctr_Ctrl',     'Neck_Ctr_Ctrl' )

        parent_controller( 'Clavicle_Lft_Ctrl', 'Chest_Ctr_Ctrl' )
        parent_controller( 'ArmUp_FK_Lft_Ctrl', 'Clavicle_Lft_Ctrl' )
        parent_controller( 'ArmLo_FK_Lft_Ctrl', 'ArmUp_FK_Lft_Ctrl' )
        parent_controller( 'Hand_FK_Lft_Ctrl',  'ArmLo_FK_Lft_Ctrl' )

        for side in ['Lft', 'Rgt']:
            for finger in ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']:
                for i in range(4):
                    parent = finger + str(i)
                    if i == 0:
                        parent = 'Hand_FK'
                    if finger == 'Thumb' and i == 3:
                        break
                    parent_controller(finger + str(i + 1) + '_' + side + '_Ctrl', parent + '_' + side + '_Ctrl' )

            parent_controller( 'Foot_IK_'     + side + '_Ctrl', 'Hips_Ctr_Ctrl' )
            parent_controller( 'FootLift_IK_' + side + '_Ctrl', 'Foot_IK_'     + side + '_Ctrl' )
            parent_controller( 'Toes_IK_'     + side + '_Ctrl', 'FootLift_IK_' + side + '_Ctrl' )
            parent_controller( 'ToesTip_IK_'  + side + '_Ctrl', 'Toes_IK_'     + side + '_Ctrl' )
            parent_controller( 'Heel_IK_'     + side + '_Ctrl', 'Foot_IK_'     + side + '_Ctrl' )
            parent_controller( 'LegPole_IK_'  + side + '_Ctrl', 'Foot_IK_'     + side + '_Ctrl' )

# Biped
#
######################################################################################

######################################################################################
#
# Anim

class Anim(Transform):

    def __init__(self):
        super( Anim, self ).__init__()

    def get_anim_curve_data( self, node ):

        dict = { }
        animObj = self.get_mobject( node )
        if animObj is not None:
            animFn = oma.MFnAnimCurve( animObj )

            dict[ 'type' ]          = curveType[ animFn.animCurveType ]

            try:
                dict[ 'input' ] = mc.listConnections( node + '.input', s=True, d=False, p=True )[0]
            except:
                pass
            try:
                dict[ 'output' ] = mc.listConnections( node + '.output', s=False, d=True, p=True )[0]
            except:
                pass

            # Pre Infinity Type
            if animFn.preInfinityType != oma.MFnAnimCurve.kConstant:
                dict[ 'pre' ]           = animFn.preInfinityType

            # Post Infinity Type
            if animFn.postInfinityType != oma.MFnAnimCurve.kConstant:
                dict[ 'post' ]          = animFn.postInfinityType

            if animFn.isWeighted:
                dict[ 'weighted' ]      = animFn.isWeighted

            dict['keys']  = {}

            times  = []
            values = []

            # Lists redundant?
            itt   = [] # In tangent type
            ott   = [] # Out tangent type
            itaw  = [] # In tangent angle Weight
            otaw  = [] # Out tangent angle weight
            itxy  = [] # In tangent XY
            otxy  = [] # Out tangent XY
            alt = []
            for i in range( 0, animFn.numKeys ):

                if dict['type'] == 'animCurveUA' or dict['type'] == 'animCurveUL':
                    time_val = animFn.input( i )
                else:
                    time_val = round( animFn.input( i ).value, 5 )

                time_tmp = time_val
                times.append ( time_tmp )
                value_tmp = animFn.value( i )

                if dict['type'] == 'animCurveTA':
                    value_tmp = math.degrees(value_tmp)

                values.append( round(value_tmp,5) )

                tmp_dict = {}

                # In Tangent type
                itt.append( animFn.inTangentType( i ) )
                ott.append( animFn.outTangentType( i ) )

                # In Tangent Angle Weight
                itaw_tmp = animFn.getTangentAngleWeight(i,True)
                itaw.append(  [itaw_tmp[0].asDegrees(), itaw_tmp[1]] )

                # Out Tangent Angle Weight
                otaw_tmp = animFn.getTangentAngleWeight(i,False)
                otaw.append( [otaw_tmp[0].asDegrees(), otaw_tmp[1]] )

                # In Tangent
                itxy.append( animFn.getTangentXY(i,True))

                # Out Tangent
                otxy.append( animFn.getTangentXY(i,False))

                tmp_dict[ 'bd' ] = animFn.isBreakdown(i)
                tmp_dict[ 'wl' ] = animFn.weightsLocked(i)
                tmp_dict[ 'tl' ] = animFn.tangentsLocked(i)

                if itt[i] != oma.MFnAnimCurve.kTangentAuto:
                    tmp_dict['itt'] = itt[i]

                if ott[i] != oma.MFnAnimCurve.kTangentAuto:
                    tmp_dict['ott'] = itt[i]

                if itaw[i][0] != 0.0:
                    tmp_dict['ia'] = round( itaw[i][0], 5 )

                if itaw[i][1] != 1.0:
                    tmp_dict['iw'] = round( itaw[i][1], 5 )

                if otaw[i][0] != 0.0:
                    tmp_dict['oa'] = round( otaw[i][0], 5 )

                if otaw[i][1] != 1.0:
                    tmp_dict['ow'] = round( otaw[i][1], 5 )

                if itxy[i][0] != 1.0:
                    tmp_dict['ix'] = round( itxy[i][0], 5 )

                if itxy[i][1] != 0.0:
                    tmp_dict['iy'] = round( itxy[i][1], 5 )

                if otxy[i][0] != 1.0:
                    tmp_dict['ox'] = round( otxy[i][0], 5 )

                if otxy[i][1] != 0.0:
                    tmp_dict['oy'] = round( otxy[i][1], 5 )

                if len ( tmp_dict ) > 0:
                    tmp_dict[ 'time' ] = times[ i ]

                    alt.append( tmp_dict )
            if len ( alt ) > 0:
                dict[ 'keys' ]['tangent'] = alt

            dict[ 'keys' ]['time'] = times
            dict[ 'keys' ]['value'] = values

        return dict

    def set_anim_curve_data( self, animCurve, data ):

        curveObj = self.get_mobject( animCurve )

        if curveObj:
            try:
                animFn = oma.MFnAnimCurve( curveObj )
                # obj = animFn.create( 4 ) # animCurveUA
            except:
                mc.warning('aniMeta: can not set MFnAnimCurve on ' + animCurve)
                return False

            animFn.setIsWeighted( data[ 'weighted' ] )
            keys = data[ 'keys' ]

            if 'time' in keys and 'value' in keys:
                times = keys[ 'time' ]
                values = keys[ 'value' ]

            if len( times ) == len( values ):
                for i in range( len( times ) ):
                    animFn.addKey( times[ i ], values[ i ] )

            if 'tangent' in keys:
                tangents = keys[ 'tangent' ]

                for i in range( len( tangents ) ):

                    tangent = tangents[ i ]

                    if 'time' in tangent:
                        # Unlock it before setting tangents
                        animFn.setTangentsLocked( i, False )
                        animFn.setWeightsLocked( i, False )

                        animFn.setTangent( i, tangent[ 'ix' ], tangent[ 'iy' ], True )  # In Tangent XY
                        animFn.setTangent( i, tangent[ 'ox' ], tangent[ 'oy' ], False )  # Out Tangent XY

                        animFn.setAngle( i, om.MAngle( math.radians( tangent[ 'ia' ] ) ), True )  # In Angle
                        animFn.setAngle( i, om.MAngle( math.radians( tangent[ 'oa' ] ) ), False )  # Out Angle

                        animFn.setWeight( i, tangent[ 'iw' ], True )  # In Weight
                        animFn.setWeight( i, tangent[ 'ow' ], False )  # Out weight

                        # Finally, set the lock state
                        animFn.setTangentsLocked( i, tangent[ 'tl' ] )
                        animFn.setWeightsLocked( i, tangent[ 'wl' ] )

                        animFn.setIsBreakdown( i, tangent[ 'bd' ] )

            return True
#
######################################################################################


######################################################################################
#
# Model

class Model(Transform):

    def __init__(self):
        super( Model, self ).__init__()

        self.tol = 0.001

    def mirror_geo(self, *args):

        sel = mc.ls(sl=True)
        # Dupliziere das Original Mesh

        for s in sel:
            dup = mc.duplicate(s)

            # SPiegel das Objekt nach -X

            # unlock attributes
            mc.setAttr( dup[0] + '.tx', lock=False )
            mc.setAttr( dup[0] + '.ty', lock=False )
            mc.setAttr( dup[0] + '.tz', lock=False )

            mc.setAttr( dup[0] + '.rx', lock=False )
            mc.setAttr( dup[0] + '.ry', lock=False )
            mc.setAttr( dup[0] + '.rz', lock=False )

            mc.setAttr( dup[0] + '.sx', lock=False )
            mc.setAttr( dup[0] + '.sy', lock=False )
            mc.setAttr( dup[0] + '.sz', lock=False )

            sx = mc.getAttr( s+'.sx' )
            mc.setAttr(dup[0] + '.scaleX', -sx)

            # Erfasse die Anzahl an UV-Koordinaten des Objekts
            uvCount = mc.polyEvaluate(dup[0], uv=True)
            # Spiegel die UVs
            mc.polyEditUV(dup[0] + '.map[0:' + str(uvCount - 1) + ']', scaleU=-1, pu=0.5, pv=0.5)

            mesh = mc.polyUnite(dup[0], sel[0], mergeUVSets=True, centerPivot=True, ch=False)

            vtxCount = mc.polyEvaluate(mesh, vertex=True)

            mergePoints = []
            myTolerence = 0.001
            for i in range(vtxCount):
                pos = mc.xform(mesh[0] + '.vtx[' + str(i) + ']', query=True, worldSpace=True, translation=True)
                if abs(pos[0]) < myTolerence:
                    mergePoints.append(mesh[0] + '.vtx[' + str(i) + ']')

            mc.polyMergeVertex(mergePoints, distance=0.001, ch=False)

            mc.select ( mesh, r=True )

    def flip_geo(self, *args ):

        sel = mc.ls(sl=True)

        if len( sel ) == 2:
            source = sel[0]
            dest = sel[1]
        else:
            source = sel[0]
            dest = sel[0]

        source_path = self.get_path( source )
        dest_path = self.get_path( dest )

        source_path.extendToShape()
        dest_path.extendToShape()

        file = mc.getAttr( source_path.fullPathName() + '.aniMetaSymFile' )

        plusX, negX, ctr = self.import_symmetry( file )

        sourceFn = om.MFnMesh( source_path )
        destFn = om.MFnMesh( dest_path )

        source_pts = sourceFn.getPoints( om.MSpace.kObject )
        dest_pts = sourceFn.getPoints( om.MSpace.kObject )

        for i in range( len ( plusX )):
            px = source_pts[ plusX[ i ] ]
            nx = source_pts[ negX[ i ] ]

            px.cartesianize()
            nx.cartesianize()

            px.x *= -1
            nx.x *= -1

            dest_pts[plusX[i]] = nx
            dest_pts[negX[i]]  = px

        for i in range(len(ctr)):
            px = source_pts[ ctr[ i ] ]
            px.x *= -1
            dest_pts[ctr[i]] = px

        destFn.setPoints( dest_pts )


    def mirror_points(self, *args, **kwargs ):

        sel = mc.ls( sl=True )

        if len( sel ) > 0:

            for s in sel:
                mc.aniMetaMirrorGeo( mesh=s  )
        else:
            print( "aniMeta: Please select a mesh with a skinCluster to mirror.")


    def get_model_sides( self, modelPath = om.MDagPath, axis=0 ):

        if mc.nodeType( modelPath.fullPathName() ) == 'mesh':

            meshFn = om.MFnMesh( modelPath )

            pts = meshFn.getPoints( space = om.MSpace.kObject )

            return self.get_sym_points( pts, axis )

        if mc.nodeType( modelPath.fullPathName() ) == 'nurbsSurface':
            surfFn = om.MFnNurbsSurface( modelPath )

            pts = surfFn.cvPositions(  )

            return self.get_sym_points( pts, axis )

    def get_sym_points( self, pts, axis=0 ):
        posX = [ ]
        negX = [ ]
        nulX = [ ]

        pts_pos = [ ]
        pts_neg = [ ]

        for i in range( len( pts ) ):

            x = pts[ i ][ axis ]

            if x > self.tol:
                posX.append( i )
            elif x < -self.tol:
                negX.append( i )
            else:
                nulX.append( i )

        sym_neg = [ ]
        x_multi, y_multi, z_multi = 1, 1, 1

        if axis==0:
            x_multi = -1
        elif axis==1:
            y_multi = -1
        elif axis==0:
            z_multi = -1

        # Loop over the indices on +X
        for i in range( len( posX ) ):

            # Set an initial high distance
            distance = 100.0
            # Set an initial "bad" index
            index = -1

            # Create a Point on -X based on +X
            posX_NEG = om.MPoint( pts[ posX[ i ] ][ 0 ] * x_multi,
                                  pts[ posX[ i ] ][ 1 ] * y_multi,
                                  pts[ posX[ i ] ][ 2 ] * z_multi)

            # Loop over the inidces on -X
            for j in range( len( negX ) ):
                # Compare the current distance to the saved distance
                if posX_NEG.distanceTo( pts[ negX[ j ] ] ) < distance:
                    # If it is closer, save the index of that point
                    index = negX[ j ]
                    # and the distance so we can compare it to other points
                    distance = posX_NEG.distanceTo( pts[ negX[ j ] ] )
            # Now uses the next matching point, is that good enough?
            if index != -1:
                sym_neg.append( index )
            else:
                mc.warning( 'aniMeta Mirror Skin: Can not find a matching -X vertex for index ', i )
                sym_neg.append( None )

        # print 'Length sym', len(posX), len(negX), len(sym_neg)
        return posX, sym_neg, nulX

    def specify_symmetry_file_ui(self, *args ):

        geos = mc.ls( sl = True ) or [ ]

        if len( geos ) > 0 :

            workDir = mc.workspace( q = True, directory = True )
            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Select',
                                     fm=1, cap = 'Specify Symmetry' )
            if result:

                self.specify_symmetry_file( result[0], geos  )
        else:
            mc.confirmDialog( message='Please select one or more meshes.',
                              title='Specify Symmetry File')

    def specify_symmetry_file( self, fileName, geos=[] ):

        for geo in geos:
            if mc.nodeType( geo ) == 'transform':
                shapes = mc.listRelatives( geo, shapes=True, pa=True ) or []

                if shapes:
                    if mc.nodeType( shapes[0]) == 'mesh' or mc.nodeType( shapes[0]) == 'nurbsSurface':
                        geo = shapes[0]

            if mc.nodeType(geo) == 'mesh' or mc.nodeType(geo) == 'nurbsSurface':

                if not mc.attributeQuery( 'aniMetaSymFile', node=geo, exists=True ):
                    mc.addAttr( geo, ln='aniMetaSymFile', dt='string' )

                mc.setAttr( geo + '.aniMetaSymFile', fileName, type='string' )

    def import_symmetry( self, *args ):

        file_name = args[0]

        if os.path.isfile( file_name ):

            with open( file_name, 'r' ) as read_file:
                data = read_file.read()

            data = json.loads( data )

            sides = data[ 'Symmetry' ][ 'Sides' ]

            length = len(sides )

            list_pos = [ ]
            list_neg = [ ]

            for i in range( length ):

                try:
                    buff = sides[ i ].split( '<>' )
                    if len( buff ) == 2:
                        list_pos.append( int(buff[ 0 ]) )
                        list_neg.append( int(buff[ 1 ]) )
                except:
                    pass


            return list_pos, list_neg, data['Symmetry']['Centre']
        else:
            mc.warning('aniMeta import symmetry file, invalid file path:', file_name)

    def duplicate_extract_soften_faces(self, *args):
        '''
        This method extracts the selected faces of a poly objects and softens it's border
        :return:
        '''

        mc.undoInfo(openChunk=True)

        iterations = 6

        selection = mc.ls(sl=True, fl=True)

        face_list = []

        obj = selection[0].split('.')[0]

        for sel in selection:
            face_list.append(int(sel.split('.')[1].split('[')[1].split(']')[0]))

        dup = mc.duplicate(obj)[0]

        cut_faces = []

        face_count = mc.polyEvaluate(f=True)

        for i in range(face_count):
            if i not in face_list:
                cut_faces.append(dup + '.f[' + str(i) + ']')

        mc.delete(cut_faces)

        face_count = mc.polyEvaluate(dup, f=True)

        sel = mc.select(dup + '.f[0:' + str(face_count - 1) + ']', r=True)

        selection = mc.ls(sl=True, fl=True)

        border_edges = mc.ls(mc.polyListComponentConversion(selection, fromFace=True, bo=True, te=True), fl=True)

        vtxs = mc.ls(mc.polyListComponentConversion(border_edges, fromEdge=True, tv=True), fl=True)

        edge = {}

        for i in range(len(border_edges)):
            edge[border_edges[i]] = mc.ls(
                mc.polyListComponentConversion(border_edges[i], fromEdge=True, bo=True, tv=True), fl=True)

        vtx_neighbor = []
        for i in range(len(vtxs)):
            neighbor = []
            for key in edge.keys():
                if vtxs[i] in edge[key]:

                    if vtxs[i] != edge[key][0]:
                        neighbor.append(edge[key][0])
                    elif vtxs[i] != edge[key][1]:
                        neighbor.append(edge[key][1])
            if len(neighbor) == 2:
                vtx_neighbor.append(neighbor)

        pos = {}
        for i in range(len(vtxs)):
            pos[str(vtxs[i])] = mc.xform(vtxs[i], q=1, t=1)
        for k in range(iterations):
            for i in range(len(vtxs)):
                pos[str(vtxs[i])][0] = pos[str(vtxs[i])][0] * 0.5 + pos[str(vtx_neighbor[i][0])][0] * 0.25 + \
                                       pos[str(vtx_neighbor[i][1])][0] * 0.25
                pos[str(vtxs[i])][1] = pos[str(vtxs[i])][1] * 0.5 + pos[str(vtx_neighbor[i][0])][1] * 0.25 + \
                                       pos[str(vtx_neighbor[i][1])][1] * 0.25
                pos[str(vtxs[i])][2] = pos[str(vtxs[i])][2] * 0.5 + pos[str(vtx_neighbor[i][0])][2] * 0.25 + \
                                       pos[str(vtx_neighbor[i][1])][2] * 0.25

        for i in range(len(vtxs)):
            mc.xform(vtxs[i], t=(pos[str(vtxs[i])][0], pos[str(vtxs[i])][1], pos[str(vtxs[i])][2]))

        mc.undoInfo(closeChunk=True)

        mc.select(dup, r=True)
        return dup
    # Model
#
######################################################################################


######################################################################################
#
# Model Symmetry Export UI

class ModelSymExportUI( Model ):

    ui_name = 'ModelSymExport'
    title = 'Export Symmetry'
    width = 300
    height = 240

    axis_ctrl = None
    file_path = None

    def __init__( self ):
        super( ModelSymExportUI, self ).__init__()

    def ui( self, *args ):

        # Loesch das Fenster, wenn es bereits existiert
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

        mc.window( self.ui_name, title = self.title, width = self.width, height = self.height, sizeable = True )

        # Layout fuer Menus
        mc.menuBarLayout()

        # Edit Menu
        mc.menu( label = 'Edit' )

        # Edit Menu Items
        mc.menuItem( label = 'Save Settings', command = self.save_settings )
        mc.menuItem( label = 'Reset Settings', command = self.reset_settings )

        # Edit Menu
        mc.menu( label = 'Help' )
        mc.menuItem( label = 'Help on ' + self.title )

        form = mc.formLayout()

        export_button = mc.button( label = self.title, command = self.export_button_cmd )
        apply_button = mc.button( label = 'Apply', command = self.apply_button_cmd )
        close_button = mc.button( label = 'Close', command = self.delete )

        axis_label = mc.text( label = 'Mirror Axis' )

        self.axis_ctrl = mc.radioButtonGrp(
            label = '',
            vertical = False,
            cw4 = (0, 40, 40, 40),
            labelArray3 = [ 'X', 'Y', 'Z' ],
            numberOfRadioButtons = 3,
            changeCommand = self.save_settings
        )

        file_path_label = mc.text( label = 'File Path' )
        self.file_path = mc.textFieldButtonGrp( text = 'Please specify a file name.',
                                                adj=1,
                                                bl='...',
                                                bc=self.select_file )

        mc.formLayout(
            form,
            edit = True,
            attachForm = [
                (axis_label, 'top', 10),
                (axis_label, 'left', 45),
                (file_path_label, 'left', 45),
                (self.file_path, 'left', 45),
                (self.file_path, 'right', 45),
                (export_button, 'bottom', 5),
                (export_button, 'left', 5),
                (close_button, 'bottom', 5),
                (close_button, 'right', 5),
                (apply_button, 'bottom', 5),
                (self.axis_ctrl, 'left', 95) ],

            attachPosition = [ (export_button, 'right', 5, 33),
                               (close_button, 'left', 5, 66),
                               (apply_button, 'right', 0, 66),
                               (apply_button, 'left', 0, 33) ],

            attachControl = [  (self.axis_ctrl, 'top', 15, axis_label),
                               (file_path_label, 'top', 15, self.axis_ctrl),
                               (self.file_path, 'top', 15, file_path_label) ]
        )
        self.restore_settings()

        mc.showWindow()

    def export_button_cmd( self, *args ):

        # Fuehrt den Mirror Befehl aus
        self.export_symmetry()

        # Schliesst das Interface
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

    def apply_button_cmd( self, *args ):

        # Fuehrt den Mirror Befehl aus
        self.export_symmetry()

    def delete( self, *args ):

        # Schliesst das Interface
        if mc.window( self.ui_name, exists = True ):
            mc.deleteUI( self.ui_name )

    def save_settings( self, *args ):

        # RadioButtonGrp indices are 1-based and the actual mode indices are zero-based
        # so we need to compensate by substracting 1
        axis = mc.radioButtonGrp( self.axis_ctrl, query = True, select = True ) -1
        file_path = mc.textFieldButtonGrp( self.file_path, query = True, text = True )

        mc.optionVar( intValue = ('aniMetaExportModelSym_Axis', axis) )
        mc.optionVar( stringValue = ('aniMetaExportModelSym_FilePath', file_path) )

    def restore_settings( self, *args ):

        if not mc.optionVar( exists = 'aniMetaExportModelSym_Axis' ):
            self.reset_settings()

        # RadioButtonGrp indices are 1-based and the actual mode indices are zero-based
        # so we need to compensate by adding 1
        axis = mc.optionVar( query = 'aniMetaExportModelSym_Axis' ) + 1
        file_path = mc.optionVar( query = 'aniMetaExportModelSym_FilePath' )

        mc.radioButtonGrp( self.axis_ctrl, edit = True, select = axis )
        mc.textFieldButtonGrp( self.file_path, edit = True, fileName = file_path )

    def reset_settings( self, *args ):

        mc.radioButtonGrp( self.axis_ctrl, edit = True, select = 1 )
        mc.textFieldButtonGrp( self.file_path, edit = True, text = 'Please specify a file name.' )

        self.save_settings()

    def select_file(self, *args):

        workDir = mc.workspace(q=True, directory=True)

        result = mc.fileDialog2(startingDirectory=workDir, fileFilter="JSON (*.json)", ds=2, okc='Save',
                                cap='Export Symmetry')

        mc.textFieldButtonGrp( self.file_path, e=True, fileName=result[0] )

        self.save_settings()

    def export_symmetry( self, *args ):

        geo = mc.ls( sl = True ) or [ ]

        if len( geo ) == 1:

            fileName = mc.textFieldButtonGrp( self.file_path, query = True, text = True )
            axis = mc.optionVar( query = 'aniMetaExportModelSym_Axis' )

            shape = self.get_path( geo[0] )
            shape.extendToShape()

            sym = self.get_model_sides( shape, axis )

            sym_list = [ ]
            for i in range( len( sym[ 0 ] ) ):
                sym_list.append( str( sym[ 0 ][ i ] ) + '<>' + str( sym[ 1 ][ i ] ) )

            vtx_count = 0

            if mc.nodeType( shape.fullPathName() ) == 'mesh':
                vtx_count = mc.polyEvaluate( shape.fullPathName(), vertex = True )

            elif mc.nodeType( shape.fullPathName() ) == 'nurbsSurface':
                surf_fn = om.MFnNurbsSurface( shape )
                vtx_count = surf_fn.numCVsInU * surf_fn.numCVsInV

            axis_name = 'X'
            if axis == 1:
                axis_name = 'Y'
            elif axis == 2:
                axis_name = 'Z'

            dict = {
                'Meta': {}
            }
            dict['Meta']['Geo'] = geo
            dict['Meta']['VertexCount'] = vtx_count
            dict['Meta']['Axis'] = axis_name
            dict['Symmetry'] = { 'Sides': sym_list, 'Centre': sym[2] }
            dict['Meta']['Type'] = mc.nodeType( shape.fullPathName() )

            flat = json.dumps( dict, indent= 4 )

            with open(fileName, 'w') as write_file:
                write_file.write( flat )

            self.specify_symmetry_file( fileName, [geo[0]] )
            print( 'Symmetry exported to file ', fileName )

        else:
            om.MGlobal.displayInfo( 'Please select a mesh to export symmetry.' )

# Transform Mirror UI
#
######################################################################################


######################################################################################
#
# Skin

class Skin(Transform):

    def __init__(self):
        super( Skin, self ).__init__()

    def get_skinning_joints(self ):

        return [
            'ArmLo_Aux1_Lft_Jnt', 'ArmLo_Aux2_Lft_Jnt', 'ArmLo_Aux3_Lft_Jnt', 'ArmLo_Blend_Lft_Jnt', 'ArmLo_Lft_Jnt',
            'ArmLo_Aux1_Rgt_Jnt', 'ArmLo_Aux2_Rgt_Jnt', 'ArmLo_Aux3_Rgt_Jnt', 'ArmLo_Blend_Rgt_Jnt', 'ArmLo_Rgt_Jnt',
            'ArmUp_Aux1_Lft_Jnt', 'ArmUp_Aux2_Lft_Jnt', 'ArmUp_Aux3_Lft_Jnt', 'ArmUp_Lft_Jnt', 'Ball_Lft_Jnt_Blend',
            'ArmUp_Aux3_Rgt_Jnt', 'ArmUp_Rgt_Jnt', 'Ball_Rgt_Jnt_Blend', 'Clavicle_Lft_Jnt', 'Eye_Lft_Jnt',
            'Chest_Jnt', 'Clavicle_Rgt_Jnt', 'Eye_Rgt_Jnt', 'Foot_Lft_Jnt_Blend', 'Foot_Rgt_Jnt_Blend',
            'Foot_Lft_Jnt', 'Foot_Rgt_Jnt', 'Hand_Lft_Jnt', 'Head_Jnt', 'Head_Jnt_Tip',  'ArmUp_Aux2_Rgt_Jnt',
            'Hand_Rgt_Jnt', 'Head_Jnt_Blend', 'Heel_Lft_Jnt', 'Hips_Jnt', 'Index1_Rgt_Jnt',  'ArmUp_Aux1_Rgt_Jnt',
            'Heel_Rgt_Jnt', 'Index1_Lft_Jnt', 'Index2_Blend_Lft_Jnt', 'Index2_Lft_Jnt', 'Index3_Blend_Lft_Jnt',
            'Index2_Blend_Rgt_Jnt', 'Index2_Rgt_Jnt', 'Index3_Blend_Rgt_Jnt', 'Index3_Rgt_Jnt', 'Index4_Blend_Rgt_Jnt',
            'Index3_Lft_Jnt', 'Index4_Blend_Lft_Jnt', 'Index4_Lft_Jnt', 'Jaw_Jnt', 'LegLo_Aux1_Lft_Jnt',
            'Index4_Rgt_Jnt', 'Jaw_Jnt_Tip', 'LegLo_Aux1_Rgt_Jnt', 'LegLo_Aux2_Rgt_Jnt', 'LegLo_Aux3_Rgt_Jnt',
            'LegLo_Aux2_Lft_Jnt', 'LegLo_Aux3_Lft_Jnt', 'LegLo_Lft_Jnt', 'LegLo_Rgt_Jnt', 'LegUp_Aux1_Lft_Jnt',
            'LegLo_Lft_Jnt_Blend', 'LegLo_Rgt_Jnt_Blend', 'LegUp_Aux1_Rgt_Jnt', 'LegUp_Aux2_Rgt_Jnt', 'LegUp_Aux3_Rgt_Jnt',
            'LegUp_Aux2_Lft_Jnt', 'LegUp_Aux3_Lft_Jnt', 'LegUp_Lft_Jnt', 'LegUp_Rgt_Jnt', 'Middle1_Lft_Jnt',
            'LegUp_Lft_Jnt_Blend', 'LegUp_Rgt_Jnt_Blend', 'Middle1_Rgt_Jnt', 'Middle2_Blend_Rgt_Jnt', 'Middle2_Rgt_Jnt',
            'Middle2_Blend_Lft_Jnt', 'Middle2_Lft_Jnt', 'Middle3_Blend_Lft_Jnt', 'Middle3_Lft_Jnt', 'Middle4_Blend_Lft_Jnt',
            'Middle3_Blend_Rgt_Jnt', 'Middle3_Rgt_Jnt', 'Middle4_Blend_Rgt_Jnt', 'Middle4_Rgt_Jnt', 'Palm_Lft_Jnt',
            'Middle4_Lft_Jnt', 'Neck_Jnt', 'Palm_Rgt_Jnt', 'Pinky1_Rgt_Jnt', 'Pinky2_Blend_Rgt_Jnt',
            'Pinky1_Lft_Jnt', 'Pinky2_Blend_Lft_Jnt', 'Pinky2_Lft_Jnt', 'Pinky3_Blend_Lft_Jnt', 'Pinky3_Lft_Jnt',
            'Pinky2_Rgt_Jnt', 'Pinky3_Blend_Rgt_Jnt', 'Pinky3_Rgt_Jnt', 'Pinky4_Blend_Rgt_Jnt', 'Pinky4_Rgt_Jnt',
            'Pinky4_Blend_Lft_Jnt', 'Pinky4_Lft_Jnt', 'Ring1_Lft_Jnt', 'Ring2_Blend_Lft_Jnt', 'Ring2_Lft_Jnt',
            'Ring1_Rgt_Jnt', 'Ring2_Blend_Rgt_Jnt', 'Ring2_Rgt_Jnt', 'Ring3_Blend_Rgt_Jnt', 'Ring3_Rgt_Jnt',
            'Ring3_Blend_Lft_Jnt', 'Ring3_Lft_Jnt', 'Ring4_Blend_Lft_Jnt', 'Ring4_Lft_Jnt',
            'Ring4_Blend_Rgt_Jnt', 'Ring4_Rgt_Jnt', 'Shoulder_Blend_Lft_Jnt', 'Spine1_Jnt', 'Spine3_Jnt',
            'Shoulder_Blend_Rgt_Jnt', 'Spine2_Jnt', 'Thumb1_Blend_Lft_Jnt', 'Thumb1_Lft_Jnt', 'Thumb2_Blend_Lft_Jnt',
            'Thumb1_Blend_Rgt_Jnt', 'Thumb1_Rgt_Jnt', 'Thumb2_Blend_Rgt_Jnt', 'Thumb2_Rgt_Jnt', 'Thumb3_Blend_Rgt_Jnt',
            'Thumb2_Lft_Jnt', 'Thumb3_Blend_Lft_Jnt', 'Thumb3_Lft_Jnt', 'ToesTip_Lft_Jnt', 'Toes_Lft_Jnt',
            'Thumb3_Rgt_Jnt', 'ToesTip_Rgt_Jnt', 'Toes_Rgt_Jnt', 'Wrist_Blend_Rgt_Jnt',
            'Wrist_Blend_Lft_Jnt'
        ]

    def bind(self, *args ):

        geos = mc.ls( sl=True )

        if len( geos ) > 0:

            char = self.get_active_char()
            joints = self.get_skinning_joints()
            print( char, geos, joints )
            if char is not None:

                infs = []

                for joint in joints:
                    inf = self.find_node( char, joint )
                    if inf is not None:
                        infs.append( inf )

                if len( joints ) == len ( infs ):

                    for geo in geos:
                        try:
                            mc.skinCluster( infs, geo, tsb=True )
                        except:
                            mc.warning( "aniMeta: There was an issue binding geo " + geo )

                    print ( "aniMeta: Bound geometry to skin. "  + str( geos ) )
        else:
            print( "aniMeta: Please select a mesh with a skinCluster to mirror.")

    def mirror(self, *args):

        sel = mc.ls( sl=True )

        if len( sel ) > 0:

            for s in sel:
                mc.aniMetaSkinMirror( mesh=s, mode=1 )
        else:
            print( "aniMeta: Please select a mesh with a skinCluster to mirror.")

    def reset( self, *args, **kwargs ):

        node = None
        if 'node' in kwargs:
            node = kwargs[ 'node' ]

        sel = [ ]

        if node is not None:
            sel.append( node )
        else:
            sel = mc.ls( sl = True ) or [ ]

        if len( sel ) > 0:
            for s in sel:
                nodes = mc.listHistory( s )
                skinC = None

                for node in nodes:
                    if mc.nodeType( node ) == 'skinCluster':
                        skinC = node

                if skinC is not None:
                    skinObj = self.get_mobject( skinC )
                    skinFn = oma.MFnSkinCluster( skinObj )

                    infs = om.MDagPathArray()

                    infs = skinFn.influenceObjects()

                    for i in range( len( infs ) ):
                        m = infs[ i ].inclusiveMatrixInverse()
                        index = skinFn.indexForInfluenceObject( infs[ i ] )
                        wimi = [ m.getElement( 0, 0 ), m.getElement( 0, 1 ), m.getElement( 0, 2 ), m.getElement( 0, 3 ),
                                 m.getElement( 1, 0 ), m.getElement( 1, 1 ), m.getElement( 1, 2 ), m.getElement( 1, 3 ),
                                 m.getElement( 2, 0 ), m.getElement( 2, 1 ), m.getElement( 2, 2 ), m.getElement( 2, 3 ),
                                 m.getElement( 3, 0 ), m.getElement( 3, 1 ), m.getElement( 3, 2 ),
                                 m.getElement( 3, 3 ) ]
                        mc.setAttr( skinFn.name() + '.bindPreMatrix[' + str( index ) + ']', wimi, type = 'matrix' )

    def smooth( self, *args ):

        sel = mc.ls( sl=True, fl=True )

        if len( sel ) > 0:

            for s in sel:
                mc.aniMetaSkinSmooth( mesh=s, weight=0.5 )
        else:
            print("aniMeta: Please select a mesh with a skinCluster to smooth.")

    def smooth_tool( self, *args):
        sel = mc.ls(sl=True, l=True) or []

        if len(sel) == 1:
            import aniMeta
            mm.eval('global string $aniMetaSmoothSkinMesh = \"' + sel[0] + '\";')

            tool_name = 'aniMetaSmoothSkinTool'

            if mc.artUserPaintCtx(tool_name, exists=True):
                mc.deleteUI(tool_name)

            #mc.artUserPaintCtx(tool_name)

            mm.eval('''
                global proc aniMetaSmoothSkin_toolSetupProc( string $toolContextName )
                {
                    python("import aniMeta");
                }
                '''
                    )
            # Init Stroke
            mm.eval('''
                global proc aniMetaSmoothSkin_initProc( int $surfaceName )
                {
                    python("aniMeta.Skin().smooth_tool_init( \\"" +$surfaceName+"\\")");
                }
                '''
                    )
            # Set Value
            mm.eval('''
                global proc aniMetaSmoothSkin_setValueProc( int $surfaceID, int $index, float $value )
                {
                    python("aniMeta.Skin().smooth_tool_set_value( " +$surfaceID+", " + $index + ", " + $value + ")");
                }
                '''
                    )
            mc.artUserPaintCtx(
                tool_name,
                #edit=True,
                toolSetupCmd='python("import aniMeta")',
                # Specifies the name of the mel script/procedure that is called once for every selected surface when an initial click is received on that surface.
                toolCleanupCmd='',
                # Specifies the name of the mel script/procedure that is called when this tool is exited.
                getSurfaceCommand='',
                # Specifies the name of the mel script/procedure that is called once for every dependency node on the selection list, whenever Artisan processes the selection list.
                getArrayAttrCommand='',
                # Specifies the name of the mel script/procedure that is called once for every surface that is selected for painting.
                initializeCmd='aniMetaSmoothSkin_initProc',
                # Specifies the name of the mel script/procedure that is called in the beginning of each stroke.
                finalizeCmd='',
                # Specifies the name of the mel script/procedure that is called at the end of each stroke.
                setValueCommand='aniMetaSmoothSkin_setValueProc',
                # Specifies the name of the mel script/procedure that is called every time a value on the surface is changed.
                getValueCommand=''
                # Specifies the name of the mel script/procedure that is called every time a value on the surface is needed by the scriptable paint tool.
            )
            mm.eval(f'catchQuiet(`setToolTo {tool_name}`);') # We do this to avoid a redundant error message
            mc.ScriptPaintToolOptions()

    def smooth_tool_init(self, surfaceName):
        # Somehow we need this, even though we aren`t really doing anything here
        pass

    def smooth_tool_set_value(self, surfaceID, index, value):
        '''
        Function called per vertex when painting weights by the Smooth Skin Tool.
        '''
        mesh = mm.eval("global string $aniMetaSmoothSkinMesh;$t=$aniMetaSmoothSkinMesh;")
        mc.aniMetaSkinSmooth(
            mesh=mesh + '.vtx[' + str(index) + ']',
            weight=value
        )

    def transfer( self, *args ):

        sel = mc.ls( sl = True )

        if len( sel ) > 1:

            #for i in range ( 1, len(sel)+1 ):
            for i in range(1, len(sel) ):

                skin = self.transfer_doit( sel[ 0 ], sel[ i ] )
                om.MGlobal.displayInfo( 'SkinCluster created: ' + skin )


            #mc.select( sel[ 1 ] )

            return skin
        else:
            mc.warning(
                "Fairyx: Please select a source mesh ( with skinning ) and a destination mesh ( without skinning )." )

    def transfer_doit( self, sourceMesh, destMesh ):

        skin1 = mm.eval( 'findRelatedSkinCluster ' + sourceMesh )


        skin2 = mm.eval( 'findRelatedSkinCluster ' + destMesh )

        if mc.objExists( skin2 ):
            mc.warning ( destMesh + ' already has a skinCluster.')
        else:
            path = self.get_path( destMesh )

            name = self.short_name( path.partialPathName() )

            path.extendToShape()

            infs = mc.skinCluster( skin1, q = True, inf = True )

            skin_method = mc.getAttr( skin1 + '.skinningMethod' )

            joints = [ ]
            xforms = [ ]

            for inf in infs:
                if mc.nodeType( inf ) == "joint":
                    joints.append( inf )
                else:
                    xforms.append( inf )

            skin2 = mc.skinCluster( joints, path.fullPathName(), name = name + '_skin', tsb = True )[ 0 ]

            mc.setAttr( skin2 + '.skinningMethod', skin_method )

            for xform in xforms:
                mc.skinCluster( skin2, e = True, ai = xform )

        try:
            mc.copySkinWeights( ss = skin1, ds = skin2, noMirror = True, surfaceAssociation = 'closestPoint',
                                influenceAssociation = 'name' )
        except:
            mc.warning( 'There was a problem transferring skinning from ' + sourceMesh + ' to ' + destMesh )

        return skin2

    ######################################################################################
    #
    # Skin I/O

    def export_ui( self, *args ):

        skins = mc.ls( sl = True ) or [ ]

        if len( skins ) == 1:

            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Save',
                                     cap = 'Save Skinning' )

            fileName = result[ 0 ]

            mc.aniMetaSkinExport( mesh = skins[0], file = fileName )

            print( 'Skin weights exported to file ', fileName )

        elif len( skins ) > 1:

            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", ds = 2, okc = 'Save', fm=3,
                                     cap = 'Save Skinning' )
            if result:
                exportDir = result[ 0 ]

                mc.waitCursor(state=True )

                for skin in skins:

                    fileName = skin
                    if ':' in fileName:
                        buff = fileName.split(':')
                        fileName = buff[len(buff)-1]

                    fileName = os.path.join( exportDir, fileName + '.json')
                    print ('\nExport Skin Weights', skin, ' -> ', fileName)
                    mc.aniMetaSkinExport(mesh=skin, file=fileName)
                mc.waitCursor(state=False )

        else:
            om.MGlobal.displayInfo( 'Please select a mesh with skinning to export.' )

    def import_ui( self, *args ):

        jnts = mc.ls( sl = True ) or [ ]

        if len( jnts ) == 1:

            workDir = mc.workspace( q = True, directory = True )

            result = mc.fileDialog2( startingDirectory = workDir, fileFilter = "JSON (*.json)", fm = 1, ds = 2,
                                     okc = 'Load', cap = 'Import Skinning' )

            fileName = result[ 0 ]

            skin = mc.aniMetaSkinImport( mesh = jnts[ 0 ], file = fileName )


            mc.skinPercent( skin[0], jnts[ 0 ], normalize=True)

            print( 'Skin weights imported from file ', fileName )

        else:
            om.MGlobal.displayInfo( 'Please select a mesh to import skinning.' )

    # Skin I/O
    #
    ##################################################################################


# Skin
#
######################################################################################

########################################################################################################################################################################################
#
# aniMetaMirrorGeo

class aniMetaMirrorGeo( om.MPxCommand ):
    __oldPoints = om.MPointArray()
    __destPath  = om.MDagPath()

    cmdName      = 'aniMetaMirrorGeo'
    version      = '1.0'

    meshFlag     = '-m'
    meshFlagLong = '-mesh'

    fileFlag     = '-f'
    fileFlagLong = '-file'

    def __init__( self ):
        om.MPxCommand.__init__( self )
        self.__mesh = None
        self.__file = None

    def isUndoable( self ):
        return True

    @staticmethod
    def creator():
        return aniMetaMirrorGeo()

    @staticmethod
    def createSyntax():
        syntax = om.MSyntax()

        syntax.addFlag( aniMetaSkinExport.meshFlag, aniMetaSkinExport.meshFlagLong, om.MSyntax.kString )
        syntax.addFlag( aniMetaSkinExport.fileFlag, aniMetaSkinExport.fileFlagLong, om.MSyntax.kString )

        return syntax

    def doIt( self, args ):

        try:
            # Get an MArgParser
            argData = om.MArgDatabase( self.syntax(), args )

        except RuntimeError:

            om.MGlobal.displayError(
                'Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.' )
            raise

        if argData.isFlagSet( self.meshFlag ):
            self.__mesh = argData.flagArgumentString( self.meshFlag, 0 )
        if argData.isFlagSet( self.fileFlag ):
            self.__file = argData.flagArgumentString( self.fileFlag, 0 )

        # print ('Mesh:', self.__mesh)
        # print ('File:', self.__file)

        self.redoIt()

    def redoIt( self ):

        sel = mc.ls(sl=True)

        if len ( sel ) > 0:
            if len( sel ) == 2:
                source = sel[0]
                dest = sel[1]
            else:
                source = sel[0]
                dest = sel[0]

            source_path = self.get_path( source )
            dest_path = self.get_path( dest )

            self.__destPath = dest_path

            source_path.extendToShape()
            dest_path.extendToShape()

            file = mc.getAttr( source_path.fullPathName() + '.aniMetaSymFile' )

            plusX, negX, ctr = self.import_symmetry( file )

            if mc.nodeType ( source_path.fullPathName() ) == 'mesh':

                sourceFn = om.MFnMesh( source_path )
                destFn = om.MFnMesh( dest_path )

                self.__oldPoints = destFn.getPoints( om.MSpace.kObject )

                source_pts = sourceFn.getPoints( om.MSpace.kObject )
                dest_pts = sourceFn.getPoints( om.MSpace.kObject )

                for i in range( len ( plusX )):
                    px = source_pts[ plusX[ i ] ]
                    px.cartesianize()
                    px.x *= -1
                    dest_pts[negX[i]]  = px

                for i in range(len(ctr)):
                    px = source_pts[ ctr[ i ] ]
                    px.x = 0.0
                    dest_pts[ctr[i]] = px

                destFn.setPoints( dest_pts )

            if mc.nodeType( source_path.fullPathName() ) == 'nurbsSurface':

                sourceFn = om.MFnNurbsSurface( source_path )
                destFn = om.MFnNurbsSurface( dest_path )

                self.__oldPoints = destFn.cvPositions(  )

                source_pts = sourceFn.cvPositions(  )
                dest_pts = sourceFn.cvPositions(  )

                for i in range( len( plusX ) ):
                    px = source_pts[ plusX[ i ] ]
                    px.cartesianize()
                    dest_pts[ plusX[ i ] ] = px

                    px.x *= -1
                    dest_pts[ negX[ i ] ] = px

                for i in range( len( ctr ) ):
                    px = source_pts[ ctr[ i ] ]
                    px.x = 0.0
                    dest_pts[ ctr[ i ] ] = px

                destFn.setCVPositions( dest_pts, om.MSpace.kWorld )

                destFn.updateSurface()

    def undoIt(self):

        destFn = om.MFnMesh( self.__destPath )
        destFn.setPoints( self.__oldPoints )

    def get_mobject( self, node ):

        try:
            list = om.MSelectionList()

            list.add( str( node ) )

            return list.getDependNode( 0 )

        except:

            pass

        return None

    def get_path( self, nodeName ):
        '''
        Returns the MDagPath of a given maya node`s string name, the verbose flag enables/disables warnings
        :rtype:
        '''

        obj = self.get_mobject( nodeName )

        if obj is not None:

            dagPath = om.MDagPath()

            if obj != om.MObject().kNullObj:
                dagPath = om.MDagPath.getAPathTo( obj )
                return dagPath

            else:
                print( 'get_path: can not get a valid MDagPath:', nodeName )

            return dagPath
        return None

    def import_symmetry( self, *args ):

        file_name = args[0]

        if os.path.isfile( file_name ):

            with open( file_name, 'r' ) as read_file:
                data = read_file.read()

            data = json.loads( data )

            sides = data[ 'Symmetry' ][ 'Sides' ]

            length = len(sides )

            list_pos = [ ]
            list_neg = [ ]

            for i in range( length ):

                try:
                    buff = sides[ i ].split( '<>' )
                    if len( buff ) == 2:
                        list_pos.append( int(buff[ 0 ]) )
                        list_neg.append( int(buff[ 1 ]) )
                except:
                    pass


            return list_pos, list_neg, data['Symmetry']['Centre']
        else:
            mc.warning('aniMeta import symmetry file, invalid file path:', file_name)
# aniMetaMirrorGeo
#
########################################################################################################################################################################################




########################################################################################################################################################################################
#
# aniMetaSkinExport

# TODO: Export/Import the skinning mode: linear, DQ etc.

class aniMetaSkinExport( om.MPxCommand ):
    __oldWeights = om.MDoubleArray()

    cmdName      = 'aniMetaSkinExport'
    version      = '1.0'

    meshFlag     = '-m'
    meshFlagLong = '-mesh'

    fileFlag     = '-f'
    fileFlagLong = '-file'

    def __init__( self ):
        om.MPxCommand.__init__( self )
        self.__mesh = None
        self.__file = None

    @staticmethod
    def creator():
        return aniMetaSkinExport()

    @staticmethod
    def createSyntax():
        syntax = om.MSyntax()

        syntax.addFlag( aniMetaSkinExport.meshFlag, aniMetaSkinExport.meshFlagLong, om.MSyntax.kString )
        syntax.addFlag( aniMetaSkinExport.fileFlag, aniMetaSkinExport.fileFlagLong, om.MSyntax.kString )

        return syntax

    def doIt( self, args ):

        arg2 = om.MArgList()

        try:
            # Get an MArgParser
            argData = om.MArgDatabase( self.syntax(), args )

        except RuntimeError:

            om.MGlobal.displayError(
                'Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.' )
            raise

        if argData.isFlagSet( self.meshFlag ):
            self.__mesh = argData.flagArgumentString( self.meshFlag, 0 )
        if argData.isFlagSet( self.fileFlag ):
            self.__file = argData.flagArgumentString( self.fileFlag, 0 )

        # print ('Mesh:', self.__mesh)
        # print ('File:', self.__file)

        self.redoIt()

    def redoIt( self ):

        self.skinExport()

    def get_mobject( self, node ):

        try:

            list = om.MSelectionList()

            list.add( str( node ) )

            obj = list.getDependNode( 0 )

            depFn = om.MFnDependencyNode( obj )

            return obj

        except:
            # om.MGlobal.displayError('Can not get an MObject from '+ node )
            pass

        return None

    def get_path( self, nodeName ):
        '''
        Returns the MDagPath of a given maya node`s string name, the verbose flag enables/disables warnings
        :rtype:
        '''

        obj = self.get_mobject( nodeName )

        if obj is not None:

            dagPath = om.MDagPath()

            if obj != om.MObject().kNullObj:
                dagPath = om.MDagPath.getAPathTo( obj )
                return dagPath

            else:
                print( 'get_path: can not get a valid MDagPath:', nodeName )

            return dagPath
        return None

    def skinExport( self ):

        skin = self.getSkin( self.__mesh )

        if skin is not None:

            skinObj = self.get_mobject( skin )

            meshPath = self.get_path( self.__mesh )

            if meshPath is None:
                mc.warning( 'aniMeta: Can not get a valid object named ', self.__mesh )
                return None

            skinFn = oma.MFnSkinCluster( skinObj )
            vtxCount = self.vertexCount()

            compFn = om.MFnSingleIndexedComponent()
            compObj = compFn.create( om.MFn.kMeshVertComponent )


            ints = om.MIntArray()

            for i in range( vtxCount ):
                ints.append( i )

            compFn.addElements( ints )

            ################################################################################
            #
            # Get Skinning Information

            infs = skinFn.influenceObjects()
            infCount = len( infs )
            infInts = om.MIntArray()
            infList = [ ]

            no = 0

            for inf in infs:
                index = skinFn.indexForInfluenceObject( inf )
                # The index does not seem to be working when it comes to getting the weights
                # so we just use a counter ( no )
                # infInts2.append( index )
                infInts.append( no )
                infList.append( AniMeta().short_name( inf.partialPathName() ) )
                # skinIndexDict[ index ] = inf.partialPathName()
                # print no, inf.partialPathName(), '\t', index
                no += 1

            # print 'infCount', infCount, 'Infs:',len(infList   ), len(infInts)

            # Get the weights as list of length components * influences
            print( '\nanim.tools: Exporting Skin Weights' )
            print( '==================================' )
            print( 'Mesh:', self.__mesh )
            print( 'Skin:', skinFn.name() )

            weights = skinFn.getWeights( meshPath, compObj, infInts )

            weighting = [ ]

            joint_names = []
            for j in range( infCount ):
                joint_names.append(AniMeta().short_name( infs[ infInts[ j ] ].partialPathName() ) )

            # Loop over Vertices

            gMainProgressBar = mm.eval('$tmp = $gMainProgressBar')
            mc.progressBar( gMainProgressBar,e=True,bp=True,ii=True,status='Getting weights',maxValue=vtxCount,step=1 )

            interrupted = False
            for i in range( vtxCount ):

                if mc.progressBar(gMainProgressBar, query=True, isCancelled=True ) :
                    mc.warning("aniMeta Export Skin Weights: process interrupted by user.")
                    return None
                mc.progressBar(gMainProgressBar, edit=True, step=1)

                dict = { }

                dict[ '@vertex' ] = i

                for j in range( infCount ):

                    weight = weights[ i * infCount + j ]

                    if weight > 0.00001:

                        jointName = joint_names[ j ]
                        dict[ jointName ] =   weight

                weighting.append( dict )

            mc.progressBar(gMainProgressBar, edit=True, endProgress=True)

            ################################################################################
            #
            # Create Weighting Information Dictionary
            weightDict = { }

            weightDict[ 'Weights' ]        = weighting
            weightDict[ 'Influences' ]     = infList
            weightDict[ 'VertexCount' ]    = vtxCount
            weightDict[ 'Name' ]           = skinFn.name()
            weightDict[ 'SkinningMethod' ] = mc.getAttr( skinFn.name() + '.skinningMethod' )

            ################################################################################
            #
            # Write to file

            jsonDump = json.dumps( weightDict, indent = 1 )

            try:
                with open( self.__file, 'w') as file_obj:
                    file_obj.write( jsonDump )
            except:
                mc.warning( 'Can not write skin file to ', self.__file )
                return False

        return True

    # Returns the vertex count of the current mesh
    def vertexCount( self ):
        meshPath = self.get_path( self.__mesh )
        if meshPath is not None:
            meshFn = om.MFnMesh( meshPath )
            return meshFn.numVertices

    # Find the Skin Cluster of the current mesh
    def getSkin( self, mesh ):

        skin = None
        # Search history closest nodes first
        his = mc.listHistory( mesh, pdo = True )

        if his:
            for h in his:
                if mc.nodeType( h ) == 'skinCluster':
                    skin = h
                    # Break on the first skin Cluster we encounter
                    break
        if skin is None:
            mc.warning( 'No skin cluster found on ', mesh )
        return skin

    # Create a Component list with all the vertex indices of a mesh
    def getComponentList( self, vtxCount ):

        compFn = om.MFnSingleIndexedComponent()
        compObj = compFn.create( om.MFn.kMeshVertComponent )
        ints = om.MIntArray()
        for i in range( vtxCount ):
            ints.append( i )
        compFn.addElements( ints )
        return compObj


# aniMetaSkinExport
#
########################################################################################################################################################################################

########################################################################################################################################################################################
#
# aniMetaSkinImport

class aniMetaSkinImport( om.MPxCommand ):
    cmdName = 'aniMetaSkinImport'
    version = '1.0'

    meshFlag = '-m'
    meshFlagLong = '-mesh'

    fileFlag = '-f'
    fileFlagLong = '-file'

    oldWeights = om.MDoubleArray()

    def __init__( self ):
        om.MPxCommand.__init__( self )
        self.__mesh = None
        self.__file = None
        self.__skin = None
        self.__infs = None
        self.__name = 'mySkinCluster#'
        self.__vtxCount = 0
        self.__weights = 0

        self.dgMod_createSkin = om.MDGModifier()
        self.dgMod_deleteSkin = om.MDGModifier()
        self.createSkin = False
        self.deleteSkin = False

        self.weightList = om.MDoubleArray()
        self.oldWeights = om.MDoubleArray()
        self.meshPath = om.MDagPath()
        self.compObj = om.MObject()
        self.infInts = om.MIntArray()
        self.infsAdded = [ ]
        self.infsRemoved = [ ]

    @staticmethod
    def creator():
        return aniMetaSkinImport()

    @staticmethod
    def createSyntax():
        syntax = om.MSyntax()
        syntax.addFlag( aniMetaSkinExport.meshFlag, aniMetaSkinExport.meshFlagLong, om.MSyntax.kString )
        syntax.addFlag( aniMetaSkinExport.fileFlag, aniMetaSkinExport.fileFlagLong, om.MSyntax.kString )
        return syntax

    def doIt( self, args ):

        #####################################################################
        # Read Flags

        arg2 = om.MArgList()

        try:
            argData = om.MArgDatabase( self.syntax(), args )

        except RuntimeError:

            om.MGlobal.displayError(
                'Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.' )
            raise

        if argData.isFlagSet( self.meshFlag ):
            self.__mesh = argData.flagArgumentString( self.meshFlag, 0 )
        if argData.isFlagSet( self.fileFlag ):
            self.__file = argData.flagArgumentString( self.fileFlag, 0 )

        #print( '\nImporting Skin Weights' )
        #print( 'Mesh:', self.__mesh )
        #print( 'File:', self.__file )

        #####################################################################
        # Read File

        try:
            with open(self.__file) as file_obj:
                data = file_obj.read()
        except:
            mc.warning( 'aniMeta import skin: Can not open file ', self.__file )
            return False

        skinWeightDict = json.loads( data )

        self.__vtxCount = skinWeightDict[ 'VertexCount' ]
        self.__weights = skinWeightDict[ 'Weights' ]
        self.__infs = skinWeightDict[ 'Influences' ]
        self.__method = skinWeightDict.setdefault(  'SkinningMethod', 0 )

        #####################################################################
        # Get Skin

        self.__skin = self.getSkin( self.__mesh )
        self.meshPath = self.get_path( self.__mesh )

        name = self.meshPath.partialPathName()
        buff = name.split('|')
        name = buff[len(buff)-1]

        self.__name = name+'_Skin'

        if self.meshPath is None:
            return None

        # We need to create a skin
        self.createSkin = True

        # if mc.objExists( self.__name) == True:
        #    mc.warning( 'There is already another node by the name of ' + self.__name )

        cmd = self.createSkinCmd( self.__mesh, self.__infs, self.__name  )

        if len( cmd ) > 0:
            self.dgMod_createSkin.commandToExecute( cmd )

        # Delete the skinCLuster if there is already one
        if self.__skin != '':
            self.deleteSkin = True
            obj = self.get_mobject( self.__skin )
            self.dgMod_deleteSkin.deleteNode( obj )

        self.redoIt()

    def find_skin( self, geo_path ):

        history = mc.listHistory( geo_path )

        if history:
            for his in history:
                if mc.nodeType( his ) == 'skinCluster':
                    return his

        return None

    def redoIt( self ):

        # Delete the current skinCLuster
        if self.deleteSkin:
            self.dgMod_deleteSkin.doIt()

        # Create a new skinCluster
        if self.createSkin:

            self.dgMod_createSkin.doIt()

            self.__name = self.find_skin( self.__mesh)

            if self.__name:
                if mc.objExists( self.__name ):

                    if mc.nodeType( self.__name ) == 'skinCluster':

                        self.__skin = self.get_mobject( self.__name )

                        #om.MGlobal.displayInfo( 'SkinCluster ' + self.__name + ' created successfully.' )

                    else:
                        mc.warning( self.__name + ' is not a skinCluster.' )
                else:
                    mc.warning( self.__name + ' does not exist.' )

        else:
            self.__name = self.getSkin( self.__mesh )
            self.__skin = self.get_mobject( self.__name )

        skinFn = oma.MFnSkinCluster( self.__skin )

        vtxCount = self.vertexCount()

        if self.__vtxCount != vtxCount:
            mc.warning( 'Vertex count does not match. Aborting skin weights import for ' + self.__name )
            return False

        #####################################################################
        # Get Influences

        infs = skinFn.influenceObjects()

        infCount = len( infs )

        # Actual Influences of the Skin Cluster
        infsList = [ ]

        for inf in infs:
            infsList.append( inf.partialPathName() )

        if len( infs ) != len( self.__infs ):
            mc.warning( 'Influence count does not match' )
            mc.warning( 'Skin Cluster Influences   ' + str( len( infs ) ) )
            mc.warning( 'Skin File    Influences ' + str( len( self.__infs ) ) )

            matchingInfs = [ ]
            missingInfs = [ ]

            #print( '\nChecking influences from file ' )
            for i in range( len( self.__infs ) ):

                if self.__infs[ i ] in infsList:
                    self.__infs[ i ] + ' has a match.'
                else:
                    print( self.__infs[ i ] + ' has no match.' )
                    missingInfs.append( self.__infs[ i ] )

            #print( '\nChecking influences from skin cluster ' )
            for i in range( len( infsList ) ):

                if infsList[ i ] in self.__infs:
                    infsList[ i ] + ' has a match.'
                else:
                    print( infsList[ i ] + ' has no match.' )
                    missingInfs.append( infsList[ i ] )

        for _inf in self.__infs:
            if _inf not in infsList:
                mc.warning( 'Joint ', _inf, 'not part of the skinCluster.' )
                return False

        #####################################################################
        # Sanity Check Data

        if self.__vtxCount != len( self.__weights ):
            mc.warning( 'Vertex count does not match weight list length.' )
            return False

        for i in range( self.__vtxCount * len( infs ) ):
            self.weightList.append( 0.0 )

        #####################################################################
        # Prepare Weights

        skinIndexDict = { }

        for inf in self.__infs:
            path = self.get_path( inf )
            index = skinFn.indexForInfluenceObject( path )
            skinIndexDict[ inf ] = index
            self.infInts.append( index )

        for i in range( len( self.__weights ) ):
            _weight = self.__weights[ i ]

            for _key in _weight.keys():

                if _key != '@vertex':
                    index = skinIndexDict[ _key ]

                    weightIndex = i * infCount + index

                    self.weightList[ weightIndex ] = _weight[ _key ]

        self.compObj = self.getComponentList( self.__vtxCount )

        skinFn = oma.MFnSkinCluster( self.__skin )

        mc.setAttr( skinFn.name() + '.skinningMethod', self.__method )

        '''
        print 'Skin:      ', skinFn.name() 
        print 'Mesh:      ', self.meshPath.partialPathName() 
        print 'Vertices  :', self.__vtxCount 
        print 'Influences:', len(self.infInts) 
        print 'Weights:   ', len(self.weightList)
        '''

        if self.__vtxCount * len( self.infInts ) == len( self.weightList ):

            try:
                skinFn.setWeights( self.meshPath, self.compObj, self.infInts, self.weightList, normalize = False )
                #print( 'Skin weights imported successfully:' + self.meshPath.partialPathName() )
                # The Normalization in the setWeights method doesnt seem to work
            except:
                raise
        else:
            mc.warning( 'Weight count does not match vertex and inf count.' )

        om.MPxCommand.setResult( skinFn.name() )

    def isUndoable( self ):
        return True

    def undoIt( self ):

        skinFn = oma.MFnSkinCluster( self.__skin )

        if self.createSkin:
            self.dgMod_createSkin.undoIt()

        if self.deleteSkin:
            self.dgMod_deleteSkin.undoIt()

        # skinFn.setWeights( self.meshPath, self.compObj, self.infInts, self.oldWeights )

    def get_mobject( self, node ):

        if mc.objExists( node ):

            try:

                list = om.MSelectionList()

                list.add( str( node ) )

                obj = list.getDependNode( 0 )

                depFn = om.MFnDependencyNode( obj )

                return obj

            except:
                om.MGlobal.displayError( 'Can not get an MObject from ' + node )
                pass
        else:
            mc.warning( 'get_mobject: Node does not exist:', node )
        return None

    def get_path( self, nodeName ):
        '''
        Returns the MDagPath of a given maya node`s string name, the verbose flag enables/disables warnings
        :rtype:
        '''

        obj = self.get_mobject( nodeName )

        if obj is not None:

            depFn = om.MFnDependencyNode( obj )

            dagPath = om.MDagPath()

            if obj != om.MObject().kNullObj:
                dagPath = om.MDagPath.getAPathTo( obj )
                return dagPath

            else:
                print( 'get_path: can not get a valid MDagPath:', nodeName )

            return dagPath
        return None

    def vertexCount( self ):
        meshPath = self.get_path( self.__mesh )
        meshFn = om.MFnMesh( meshPath )
        return meshFn.numVertices

    def getSkin( self, mesh ):
        skin = ''
        his = mc.listHistory( mesh, pdo = True ) or [ ]
        for h in his:
            if mc.nodeType( h ) == 'skinCluster':
                skin = h
                break
        return skin

    def getComponentList( self, vtxCount ):
        compFn = om.MFnSingleIndexedComponent()
        compObj = compFn.create( om.MFn.kMeshVertComponent )
        ints = om.MIntArray()
        for i in range( vtxCount ):
            ints.append( i )
        compFn.addElements( ints )
        return compObj

    def createSkinCmd( self, geo, joints, skinName = 'skinCluster#' ):

        allowedInfTypes = [ 'transform', 'joint' ]

        cmd = [ ]

        if len( joints ) > 0 and mc.objExists( geo ):

            missingJoints = [ ]
            wrongType = [ ]

            # Check if inf exists
            # Check if type is okay
            for joint in joints:
                if not mc.objExists( joint ):
                    missingJoints.append( joint )
                else:
                    if mc.nodeType( joint ) not in allowedInfTypes:
                        wrongType.append( joint )

            # Inform user
            if len( missingJoints ) > 0:
                for joint in missingJoints:
                    mc.warning( 'Can not find influence ' + joint )

            # Inform user
            if len( wrongType ) > 0:
                for joint in wrongType:
                    mc.warning( 'Wrong influence type ' + joint )

            # Create Command
            if len( missingJoints ) == 0 and len( wrongType ) == 0:

                if mc.objExists( skinName ) == True:

                    index = 1
                    objExists = True

                    while objExists:

                        if not mc.objExists( skinName + str(index)):
                            break
                        else:
                            index += 1
                    skinName = skinName+str(index)

                cmd = 'optionVar -sv "atSkinClusterName" `skinCluster -tsb -name "' + skinName + '" '
                for i in range( len( joints ) ):
                    cmd += joints[ i ] + ' '
                cmd += geo + '`'
        else:
            if len( joints ) == 0:
                mc.warning( 'Please specifiy joints for the skinCluster.' )
            if not mc.objExists( geo ):
                mc.warning( 'Geometry ' + geo + ' does not exist.' )


        return cmd


# aniMetaSkinImport
#
########################################################################################################################################################################################


########################################################################################################################################################################################
#
# aniMetaSkinMirror

class aniMetaSkinMirror( om.MPxCommand ):
    cmdName = 'aniMetaSkinMirror'
    version = '1.0'

    kMeshFlag = '-m'
    kMeshFlagLong = '-mesh'

    kModeFlag = '-md'
    kModeFlagLong = '-mode'

    oldWeights = om.MDoubleArray()
    tol = 0.00001

    def __init__( self ):
        om.MPxCommand.__init__( self )
        self.__mesh = None
        self.__mode = None
        self.__skin = None
        self.__infs = None
        self.__vtxCount = 0
        self.__weights = 0

        self.new_weights = om.MDoubleArray()
        self.old_weights = om.MDoubleArray()
        self.modelPath = om.MDagPath()
        self.compObj = om.MObject()
        self.infInts = om.MIntArray()
        self.infIntsMirror = om.MIntArray()

    @staticmethod
    def creator():
        return aniMetaSkinMirror()

    @staticmethod
    def createSyntax():
        syntax = om.MSyntax()
        syntax.addFlag( aniMetaSkinMirror.kMeshFlag, aniMetaSkinMirror.kMeshFlagLong, om.MSyntax.kString )
        syntax.addFlag( aniMetaSkinMirror.kModeFlag, aniMetaSkinMirror.kModeFlagLong, om.MSyntax.kLong )
        return syntax

    def doIt( self, args ):

        #####################################################################
        # Read Flags

        arg2 = om.MArgList()

        try:
            argData = om.MArgDatabase( self.syntax(), args )

        except RuntimeError:

            om.MGlobal.displayError(
                'Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.' )
            raise

        if argData.isFlagSet( self.kMeshFlag ):
            self.__mesh = argData.flagArgumentString( self.kMeshFlag, 0 )
        if argData.isFlagSet( self.kModeFlag ):
            self.__mode = argData.flagArgumentString( self.kModeFlag, 0 )

        print( '\nMirror Skin Weights' )
        print( 'Mesh:', self.__mesh )
        print( 'Mode:', self.__mode )

        self.modelPath = self.get_path( self.__mesh )

        if mc.nodeType( self.modelPath.fullPathName() ) != 'mesh':
            self.modelPath.extendToShape()

        if mc.nodeType( self.modelPath.fullPathName() ) != 'mesh':
            mc.warning( 'aniMetaSkinMirror: ' + self.modelPath.fullPathName() + ' is not a mesh.' )
            return None

        self.redoIt()

    def redoIt( self ):

        self.__skin = self.get_skin( self.modelPath, asString = False )

        if self.__skin is not None:

            warnUser = False

            skinFn = oma.MFnSkinCluster( self.__skin )

            # Get All Influences
            influencePaths = skinFn.influenceObjects()

            # Get a list of mirrored influence names Lft <> Rgt
            influenceMirrorPaths = self.get_mirror_infs( influencePaths )

            # Get the index on the skinCluster for each influence
            for i, inf in enumerate( influencePaths ):
                self.infInts.append( skinFn.indexForInfluenceObject( inf ) )
                self.infIntsMirror.append( skinFn.indexForInfluenceObject( influenceMirrorPaths[ i ] ) )

            # Get the vertex count of the mesh
            self.__vtxCount = mc.polyEvaluate( self.modelPath.fullPathName(), vertex = True )

            # Get a vertex component object
            compObj = self.get_comp_obj( self.__vtxCount )

            # Get the weights
            self.old_weights = skinFn.getWeights( self.modelPath, compObj )

            # Copy the weights
            self.new_weights.copy( self.old_weights[ 0 ] )

            if mc.attributeQuery( 'aniMetaSymFile', node=self.modelPath.fullPathName(), exists=True  ):

                # Get the symmetry from a file containing that information
                file_name = mc.getAttr( self.modelPath.fullPathName() + '.aniMetaSymFile' )
                #print ('aniMeta Skinning: using file', file_name )

                data =  Model().import_symmetry( file_name )
                vertexPlus  = data[0]                       # Vertices on X > 0
                vertexMinus = data[1]                       # Vertices on X < 0
                vertexNull  = data[2]                       # Vertices on X == 0

            else:
                # Get the symmetry based on the topology
                vertexPlus, vertexMinus, vertexNull = self.get_model_sides( self.modelPath )

            if len( vertexPlus ) != len( vertexMinus ):
                print( 'Symmetry Report: ' + self.modelPath.partialPathName() )
                print( 'Vertices on +X:  ' + str( len( vertexPlus ) ) )
                print( 'Vertices on -X:  ' + str( len( vertexMinus ) ) )
                mc.warning( 'Mirror Skin Weights: model is not symmetrical, mirroring aborted.' )
                return None
            else:
                # joint count
                infCount = len( influencePaths )

                # Loop over Vertices in +X
                for i in range( len( vertexPlus ) ):

                    if vertexMinus[ i ] is None:
                        mc.warning( 'aniMeta Mirror Skin: skipping vertex ', vertexPlus[ i ], ', no mirror match found.' )
                        warnUser = True
                    else:
                        # Offset for the array vertexCount * influenceCount
                        offsetPlus  = vertexPlus [ i ] * infCount
                        offsetMinus = vertexMinus[ i ] * infCount

                        # Loop over influences to reset the skinning on -X?

                        for j in range( infCount ):
                            #print j, vertexPlus[ i ], vertexMinus[ i ]
                            if vertexPlus[ i ] != vertexMinus[ i ]:
                                mirror_index = self.infIntsMirror[ j ]
                                new_weight_index = offsetMinus + mirror_index
                                try:
                                    self.new_weights[ new_weight_index ] = 0
                                except:
                                    print (len( self.new_weights ), new_weight_index)

                        # Loop over influences to mirror skinning from +X to -X
                        for k in range( infCount ):

                            weight = self.new_weights[ offsetPlus + k ]

                            indexMinus = offsetMinus + self.infIntsMirror[ k ]
                            indexPlus  = offsetMinus + self.infInts[ k ]            # maybe this shoould be offsetPlus?

                            # No Mirror
                            if influencePaths == influenceMirrorPaths:
                                self.new_weights[ indexMinus ] = weight

                            # Mirror
                            else:
                                # Standard Mirror +X > -X
                                if vertexPlus[ i ] != vertexMinus[ i ]:
                                    #print 'case 1'
                                    self.new_weights[ indexMinus ] = weight

                # Loop over Vertices on X == 0
                for i in range( len( vertexNull ) ):

                    offset = vertexNull [ i ] * infCount

                    # Loop over influences to split the difference
                    for k in range( infCount ):

                        inf_index        = k
                        inf_index_mirror = self.infIntsMirror[ k ]

                        # Get the weight for the current influence and its matching mirror
                        weight        = self.new_weights[ offset + inf_index ]
                        weight_mirror = self.new_weights[ offset + inf_index_mirror  ]

                        # Average their combined weight
                        weight_average = ( weight + weight_mirror ) * 0.5

                        # Set the result to both of them
                        self.new_weights[ offset + inf_index ]         = weight_average
                        self.new_weights[ offset + inf_index_mirror  ] = weight_average

                self.compObj = self.get_comp_list( self.__vtxCount )

                print ('Skin:      ', skinFn.name())
                print ('Mesh:      ', self.modelPath.partialPathName())
                print ('CompObj:   ', om.MFnSingleIndexedComponent( compObj ).elementCount)
                print ('Weights:   ', len( self.new_weights ))

                self.old_weights = skinFn.setWeights( self.modelPath,
                                                      self.compObj,
                                                      self.infInts,
                                                      self.new_weights,
                                                      normalize = True,
                                                      returnOldWeights = True )
                if warnUser == False:
                    om.MGlobal.displayInfo( 'aniMeta: Skin weights mirrored successfully.' )
                else:
                    mc.confirmDialog(
                        message = 'There were issues mirroring skin weights,\nplease check the Script Editor for details.',
                        button = 'Okay' )

    def isUndoable( self ):
        return True

    def undoIt( self ):

        skinFn = oma.MFnSkinCluster( self.__skin )

        skinFn.setWeights( self.modelPath,
                           self.compObj,
                           self.infInts,
                           self.old_weights,
                           normalize = True,
                           returnOldWeights = False )

    def get_mobject( self, node ):

        if mc.objExists( node ):

            try:

                list = om.MSelectionList()

                list.add( str( node ) )

                obj = list.getDependNode( 0 )

                depFn = om.MFnDependencyNode( obj )

                return obj

            except:
                om.MGlobal.displayError( 'Can not get an MObject from ' + node )
                pass
        else:
            mc.warning( 'get_mobject: Node does not exist:', node )
        return None

    def get_path( self, nodeName ):
        '''
        Returns the MDagPath of a given maya node`s string name, the verbose flag enables/disables warnings
        :rtype:
        '''
        obj = self.get_mobject( nodeName )

        if obj is not None:

            depFn = om.MFnDependencyNode( obj )

            dagPath = om.MDagPath()

            if obj != om.MObject().kNullObj:
                dagPath = om.MDagPath.getAPathTo( obj )
                return dagPath

            else:
                print( 'get_path: can not get a valid MDagPath:', nodeName )

            return dagPath
        return None

    def get_skin( self, modelPath, asString = True ):
        '''
        Returns the skinCluster of a given mesh.
        :param modelPath: the mesh as a MDagPath extended to the shape
        :param asString: if true returns the skinCLuster name a string, otherwise as MObject
        :return: the skinCLuster as a string, if none is found returns None.
        '''
        iter = om.MItDependencyNodes( om.MFn.kSkinClusterFilter )

        while not iter.isDone():
            skinObj = iter.thisNode()
            skinFn = oma.MFnSkinCluster( skinObj )

            out = skinFn.numOutputConnections()

            for i in range( out ):
                skinPath = skinFn.getPathAtIndex( i )
                if modelPath == skinPath:
                    if asString:
                        return skinFn.name()
                    else:
                        return skinObj

            iter.next()
        return None

    def get_mirror_infs( self, infs = om.MDagPathArray ):

        mirrors = [ ]

        for inf in infs:

            name = ''

            ls = inf.partialPathName().split( '_' )

            # Not pretty, i know ...
            lfts = [ 'l', 'L', 'Lft', 'LFT', 'Left', 'LEFT', 'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L01', 'L02', 'L03', 'L04' ]
            rgts = [ 'r', 'R', 'Rgt', 'RGT', 'Right', 'RIGHT', 'R0', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R01', 'R02', 'R03', 'R04' ]

            for i, l in enumerate( ls ):

                token = l

                if l in lfts:
                    index = lfts.index( l )
                    token = rgts[ index ]

                if l in rgts:
                    index = rgts.index( l )
                    token = lfts[ index ]

                if i == 0:
                    name = token
                else:
                    name += '_' + token
            match = False

            for path in infs:
                if path.partialPathName() == name:

                    mirrors.append( path )
                    match = True

            # If there is no match, append the original influence, because it is probably a centre inf
            if not match:
                mc.warning( 'No matching mirror inf found for ' + inf.partialPathName() )
                mirrors.append( inf )
        for i, inf in enumerate(mirrors):
            print(infs[i].partialPathName(), mirrors[i].partialPathName())

        return mirrors

    def get_comp_obj( self, count ):
        compFn = om.MFnSingleIndexedComponent()
        compObj = compFn.create( om.MFn.kMeshVertComponent )

        ints = om.MIntArray()

        for i in range( count ):
            ints.append( i )

        compFn.addElements( ints )
        return compObj

    def get_model_sides( self, modelPath = om.MDagPath ):

        if mc.nodeType( modelPath.fullPathName() ) == 'mesh':

            meshFn = om.MFnMesh( modelPath )
            pts = meshFn.getPoints( space = om.MSpace.kObject )

            return self.find_sym_points( pts )
        if mc.nodeType( modelPath.fullPathName() ) == 'nurbsSurface':
            meshFn = om.MFnNurbsSurface( modelPath )
            pts = meshFn.cvPositions( )

            return self.find_sym_points( pts )

    def find_sym_points( self, pts=[] ):

        posX = [ ]
        negX = [ ]
        nulX = [ ]

        for i in range( len( pts ) ):

            x = pts[ i ][ 0 ]

            if x > self.tol:
                posX.append( i )
            elif x < -self.tol:
                negX.append( i )
            else:
                nulX.append( i )

        sym_neg = [ ]

        # Loop over the indices on +X
        for i in range( len( posX ) ):

            # Set an initial high distance
            distance = 100.0
            # Set an initial "bad" index
            index = -1

            # Create a Point on -X based on +X
            posX_NEG = om.MPoint( -pts[ posX[ i ] ][ 0 ], pts[ posX[ i ] ][ 1 ], pts[ posX[ i ] ][ 2 ] )

            # Loop over the indices on -X
            for j in range( len( negX ) ):
                # Compare the current distance to the saved distance
                if posX_NEG.distanceTo( pts[ negX[ j ] ] ) < distance:
                    # If it is closer, save the index of that point
                    index = negX[ j ]
                    # and the distance so we can compare it to other points
                    distance = posX_NEG.distanceTo( pts[ negX[ j ] ] )
            # Now uses the next matching point, is that good enough?
            if index != -1:
                sym_neg.append( index )
            else:
                mc.warning( 'aniMeta Mirror Skin: Can not find a matching -X vertex for index ', i )
                sym_neg.append( None )

        return posX, sym_neg, nulX

    def get_comp_list( self, vtxCount ):
        compFn = om.MFnSingleIndexedComponent()
        compObj = compFn.create( om.MFn.kMeshVertComponent )
        ints = om.MIntArray()
        for i in range( vtxCount ):
            ints.append( i )
        compFn.addElements( ints )
        return compObj


# aniMetaSkinMirror
#
########################################################################################################################################################################################


########################################################################################################################################################################################
#
# aniMetaSkinSmooth

class aniMetaSkinSmooth( om.MPxCommand ):
    cmdName = 'aniMetaSkinSmooth'

    meshFlag = '-m'
    meshFlagLong = '-mesh'

    weightFlag = '-w'
    weightFlagLong = '-weight'

    def __init__( self ):
        om.MPxCommand.__init__( self )
        self.__mesh = None
        self.__meshPath = om.MDagPath()
        self.__vertex = None
        self.__skin = None
        self.__newWeights = om.MDoubleArray()
        self.__oldWeights = [ ]
        self.__infs = om.MIntArray()
        self.__weight = 0.5

    @staticmethod
    def creator():
        return aniMetaSkinSmooth()

    @staticmethod
    def createSyntax():

        syntax = om.MSyntax()
        syntax.addFlag( aniMetaSkinSmooth.meshFlag, aniMetaSkinSmooth.meshFlagLong, om.MSyntax.kString )
        syntax.addFlag( aniMetaSkinSmooth.weightFlag, aniMetaSkinSmooth.weightFlagLong, om.MSyntax.kDouble )

        return syntax

    def doIt( self, args ):

        ###################################################################################
        #
        # Arguments

        try:
            argData = om.MArgDatabase( self.syntax(), args )

        except RuntimeError:

            om.MGlobal.displayError(
                'Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.' )
            raise

        # Mesh
        if argData.isFlagSet( self.meshFlag ):
            self.__mesh = argData.flagArgumentString( self.meshFlag, 0 )

        # Vertex
        if argData.isFlagSet( self.weightFlag ):
            self.__weight = argData.flagArgumentString( self.weightFlag, 0 )

        # Arguments
        #
        ###################################################################################

        ###################################################################################
        #
        # Get Mesh and Components

        selList = om.MSelectionList()

        try:
            selList.add( self.__mesh )
        except:
            mc.warning( self.cmdName, ' can not find node', self.__mesh )
            raise

        # Tupel mit DagPath und kMeshVertComponent
        cmp = selList.getComponent( 0 )

        self.__meshPath = cmp[ 0 ]
        self.__vertex = cmp[ 1 ]

        ###################################################################################
        # Get Skin

        if self.__meshPath is None:
            mc.warning( 'aniMeta Smooth Skin: object does not exist ', self.__mesh )
            return None

        self.__skin = self.get_skin( self.__meshPath, asString = False )

        if self.__skin is None:
            mc.warning( 'aniMeta Smooth Skin: can not find skinCLuster in mesh ', self.__mesh )
            return None

        skinFn = oma.MFnSkinCluster( self.__skin )

        #####################################################################
        # Get Connected Vertices

        neighborVtx = om.MItMeshVertex( self.__meshPath, self.__vertex ).getConnectedVertices()
        neighborCount = len( neighborVtx )

        compFn = om.MFnSingleIndexedComponent()
        compObj = compFn.create( self.__vertex.apiType() )
        compFn.addElements( neighborVtx )

        #####################################################################
        # Get Old Weights

        self.__oldWeights = skinFn.getWeights( self.__meshPath, self.__vertex )
        neighborWeights = skinFn.getWeights( self.__meshPath, compObj )
        infCount = self.__oldWeights[ 1 ]

        #####################################################################
        # Get Influences

        influencePaths = skinFn.influenceObjects()

        # Get the index for each influence
        for i, inf in enumerate( influencePaths ):
            self.__infs.append( skinFn.indexForInfluenceObject( inf ) )

        ####################################################################
        # Calculate Average to neighboring vertices

        weight = float( self.__weight )

        for i in range( infCount ):
            self.__newWeights.append( 0.0 )

            neighbor = 0

            for j in range( neighborCount ):
                neighbor += neighborWeights[ 0 ][ j * infCount + i ]

            if neighbor > 0.0 or self.__oldWeights[ 0 ][ i ] > 0.0:
                neighbor /= neighborCount

                newWeight = (1 - weight) * self.__oldWeights[ 0 ][ i ] + weight * neighbor

                self.__newWeights[ i ] = newWeight

        ###########################################################################
        # Normalize Weights

        totalWeight = 0

        highestIndex = 0
        highestWeight = 0

        for i in range( len( self.__newWeights ) ):
            totalWeight += self.__newWeights[ i ]

            if self.__newWeights[ i ] > highestWeight:
                highestWeight = self.__newWeights[ i ]
                highestIndex = i

        if totalWeight < 1.0:
            self.__newWeights[ highestIndex ] += (1.0 - totalWeight)

        if totalWeight > 1.0:
            self.__newWeights[ highestIndex ] -= (totalWeight - 1.0)

        self.redoIt()

    def redoIt( self ):

        skinFn = oma.MFnSkinCluster( self.__skin )

        #####################################################################
        # Set Weights

        compFn2 = om.MFnSingleIndexedComponent( self.__vertex )

        '''
        print 'mesh        ', self.__meshPath.partialPathName()
        print 'skin        ', skinFn.name()
        print '__vertex    ', len ( compFn2.getElements() )
        print '__infs      ', len ( self.__infs )
        print '__newWeights', len ( self.__newWeights )
        '''

        self.__oldWeights = skinFn.setWeights(
            self.__meshPath,
            self.__vertex,
            self.__infs,
            self.__newWeights,
            normalize = True,
            returnOldWeights = True
        )

    def isUndoable( self ):
        return True

    def undoIt( self ):

        try:
            skinFn = oma.MFnSkinCluster( self.__skin )

            skinFn.setWeights( self.__meshPath,
                               self.__vertex,
                               self.__infs,
                               self.__oldWeights,
                               normalize = True,
                               returnOldWeights = False )
        except:
            mc.warning( self.cmdName, 'There was a problem undoing the smooth skin cmd.' )
            raise

    def get_skin( self, modelPath, asString = True ):
        '''
        Returns the skinCluster of a given mesh.
        :param modelPath: the mesh as a MDagPath extended to the shape
        :param asString: if true returns the skinCLuster name a string, otherwise as MObject
        :return: the skinCLuster as a string, if none is found returns None.
        '''
        iter = om.MItDependencyNodes( om.MFn.kSkinClusterFilter )

        while not iter.isDone():
            skinObj = iter.thisNode()
            skinFn = oma.MFnSkinCluster( skinObj )

            out = skinFn.numOutputConnections()

            for i in range( out ):
                skinPath = skinFn.getPathAtIndex( i )
                if modelPath == skinPath:
                    if asString:
                        return skinFn.name()
                    else:
                        return skinObj

            iter.next()
        return None


########################################################################################################################################################################################
#
# Initialize
selection_changed_callback = None

scriptJobIds = []

def initializePlugin( mobject ):
    mplugin = om.MFnPlugin( mobject, "Jan Berger", kPluginVersion, "Any" )

    #selection_changed_callback = om.MEventMessage.addEventCallback( "NewSceneOpened", char_list_refresh )

    # Create Menu
    Menu().create()

    # Create Tool Panel
    AniMeta().update_ui()

    ###############################################################################
    # Add plug-in Path to Path environment variable
    fileName = inspect.getfile( inspect.currentframe() )

    dirName = os.path.dirname( fileName )

    sys.path.append( dirName )

    # Add plug-in Path to Path environment variable
    ###############################################################################

    # Refresh the python module upon reload
    #import aniMeta
    #reload( aniMeta )

    try:
        mplugin.registerCommand( aniMetaMirrorGeo.cmdName, aniMetaMirrorGeo.creator, aniMetaMirrorGeo.createSyntax )
    except:
        sys.stderr.write( "Failed to register command: %s\n" % aniMetaMirrorGeo.cmdName )
        raise

    try:
        mplugin.registerCommand( aniMetaSkinExport.cmdName, aniMetaSkinExport.creator, aniMetaSkinExport.createSyntax )
    except:
        sys.stderr.write( "Failed to register command: %s\n" % aniMetaSkinExport.cmdName )
        raise

    try:
        mplugin.registerCommand( aniMetaSkinImport.cmdName, aniMetaSkinImport.creator, aniMetaSkinImport.createSyntax )
    except:
        sys.stderr.write( "Failed to register command: %s\n" % aniMetaSkinImport.cmdName )
        raise

    try:
        mplugin.registerCommand( aniMetaSkinMirror.cmdName, aniMetaSkinMirror.creator, aniMetaSkinMirror.createSyntax )
    except:
        sys.stderr.write( "Failed to register command: %s\n" % aniMetaSkinMirror.cmdName )
        raise

    try:
        mplugin.registerCommand( aniMetaSkinSmooth.cmdName, aniMetaSkinSmooth.creator, aniMetaSkinSmooth.createSyntax )
    except:
        sys.stderr.write( "Failed to register command: %s\n" % aniMetaSkinSmooth.cmdName )
        raise

    # Create a scriptJob to update the UI when a file has been opened
    # sciptJobID = mc.scriptJob(e=["SceneOpened", "import aniMeta\naniMeta.char_list_refresh()"], protected=True)

    om.MGlobal.displayInfo( kPluginName + ' Version ' + kPluginVersion + ' loaded.' )

    scriptJobIds.append( mc.scriptJob( event = [ 'NewSceneOpened', AniMeta().update_ui ] ) )
    scriptJobIds.append( mc.scriptJob( event = [ 'SceneOpened', AniMeta().update_ui ] ) )
    scriptJobIds.append( mc.scriptJob( event = [ 'Undo', AniMeta().update_ui ] ) )

# Initialize
#
########################################################################################################################################################################################

########################################################################################################################################################################################
#
# Uninitialize

def uninitializePlugin( mobject ):

    Menu().delete()
    '''
    try:
        om.MMessage.removeCallback( char_list_refresh )
    except:
        pass

    animTool.menu_delete()
    animTool.ui_delete()
    '''

    TransformMirrorUI().delete()

    mplugin = om.MFnPlugin( mobject )
    try:
        mplugin.deregisterCommand( aniMetaSkinExport.cmdName )
    except:
        sys.stderr.write( "Failed to unregister command: %s\n" % aniMetaSkinExport.cmdName )
        raise

    try:
        mplugin.deregisterCommand( aniMetaMirrorGeo.cmdName )
    except:
        sys.stderr.write( "Failed to unregister command: %s\n" % aniMetaMirrorGeo.cmdName )
        raise
    try:
        mplugin.deregisterCommand( aniMetaSkinImport.cmdName )
    except:
        sys.stderr.write( "Failed to unregister command: %s\n" % aniMetaSkinImport.cmdName )
        raise

    try:
        mplugin.deregisterCommand( aniMetaSkinMirror.cmdName )
    except:
        sys.stderr.write( "Failed to unregister command: %s\n" % aniMetaSkinMirror.cmdName )
        raise

    try:
        mplugin.deregisterCommand( aniMetaSkinSmooth.cmdName )
    except:
        sys.stderr.write( "Failed to unregister command: %s\n" % aniMetaSkinSmooth.cmdName )
        raise

    om.MGlobal.displayInfo( kPluginName + ' Version ' + kPluginVersion + ' unloaded.' )

    # Delete Script Jobs
    for id in scriptJobIds:
        try:
            mc.scriptJob( kill = id, force=True )
        except:
            pass

    # Delete UI
    if mc.workspaceControl( 'aniMetaUIWorkspaceControl', exists = True ):
        mc.deleteUI( 'aniMetaUIWorkspaceControl' )

    if mc.window( AniMetaOptionsUI.name, exists=True ):
        mc.deleteUI( AniMetaOptionsUI.name )

    if mc.window(BlendShapeSplitter.ui_name, exists=True):
        mc.deleteUI(BlendShapeSplitter.ui_name)

# Unininitialize
#
########################################################################################################################################################################################

########################################################################################################################################################################################
#
# UI

class AniMetaUI( MayaQWidgetDockableMixin, QWidget):

    createTab = None
    libTab    = None
    mainTab   = None
    charList  = None
    ui_name   = 'aniMetaUI'

    def __init__(self, parent=None, create=True ):

        super(AniMetaUI, self).__init__(parent=parent)
        self.am = AniMeta()

        if create:
            self.ui_create()

    def char_list_refresh( self, *args, **kwargs ):

        char_list = None

        if len(args) > 0:
            char_list = args[0]
        else:
            char_list = self.get_char_list()

        if char_list is not None:
            char_list.clear()

            bipeds = self.am.get_nodes(None, {'Type': kBipedRoot})
            quadrupeds = self.am.get_nodes(None, {'Type': kQuadrupedRoot})
            nodes = bipeds + quadrupeds
            if len(nodes):
                for node in nodes:
                    char_list.addItem(node)

    def get_active_char( self ):
        '''
        Gets the selected character from the character list.
        :return: the selected character
        '''

        list = self.get_char_list()

        if list is not None:
            count = list.count()
            if count > 0:
                char = list.currentText()
                if mc.objExists(char):
                    return char
                else:
                    return None
        else:
            return None

    def get_char_list( self, *args ):
        char_list = None
        ptr = None
        try:
            ptr = omui.MQtUtil.findControl('aniMetaUI')
        except:
            mc.warning('aniMeta find char: Can not find UI.')
            return None
        widget = None 
        try:
            widget = wrapInstance( long( ptr ), QWidget )
        except: 
            '''
            mc.warning('aniMeta find char: Can not wrap swip object.' + str(args))
            return None
            '''
            pass
        if widget is None:
            try:
                widget = wrapInstance( int( ptr ), QWidget )
            except:
                pass
            
        if widget is not None:
            char_list = None
            try:
                char_list = widget.findChild(QComboBox, 'aniMetaCharList')

            except:
                mc.warning('aniMeta find char: Can not find character list.')
                return None

        return char_list

    def list_change( self, *args):
        char = self.charList.currentText()
        self.mainTab.ui_update( char )

    def maya_main_window( self ):
        main_window_ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(long(main_window_ptr), QWidget)

    def ui_create( self, restore=False):

        if restore:
            # Grab the created workspace control with the following.
            restoredControl = omui.MQtUtil.getCurrentParent()
        else:
            self.ui_delete()

        if mc.workspaceControl( self.ui_name + 'WorkspaceControl', exists=True ):
            mc.deleteUI (self.ui_name + 'WorkspaceControl')

        self.setObjectName(self.ui_name)
        self.setWindowTitle('aniMeta')

        margin = 4

        # Main Layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)
        self.setMinimumWidth( 600 )
        self.setMinimumHeight( 600 )

        self.menubar = QMenuBar()
        optionsMenu = self.menubar.addMenu('&Options')
        self.main_layout.addWidget(self.menubar)

        # Select
        select = QAction( self, text='Select', triggered=self.menu_select )
        optionsMenu.addAction( select )

        # Rename
        rename = QAction( self, text='Rename', triggered=self.menu_rename )
        optionsMenu.addAction( rename )

        # Duplicate
        duplicate = QAction( self, text='Duplicate', triggered=self.menu_duplicate )
        optionsMenu.addAction( duplicate )

        # Delete
        delete = QAction( self, text='Delete', triggered=self.menu_delete )
        optionsMenu.addAction( delete )

        help = QAction("Help",self)
        self.menubar.addAction(help)

        ################################################################################################################
        #
        # Top Bar

        # aniMeta Label
        textLabel = QLabel('aniMeta ' + kPluginVersion + ' by Jan Berger')
        textLabel.setMargin(margin)
        self.main_layout.addWidget(textLabel)

        # Horizontal Layout for Character
        self.top_bar_layout = QHBoxLayout()
        self.main_layout.addLayout(self.top_bar_layout)

        # Character Label
        label = QLabel('Character')
        self.top_bar_layout.addWidget(label)
        label.setMargin(margin)

        # Character List
        self.charList = QComboBox()
        self.charList.currentIndexChanged.connect(self.list_change)
        self.charList.setObjectName('aniMetaCharList')
        self.top_bar_layout.addWidget(self.charList)

        data = {
            'charList': self.charList
        }

        refreshButton = QPushButton("Refresh", self)
        refreshButton.setFixedWidth(px(72))
        refreshButton.setFixedHeight(px(32))
        refreshButton.setStyleSheet(
            "QPushButton {background-color: #666666; border-radius: 3px;}"
            "QPushButton:hover {background-color: #777777; }"
        )
        refreshButton.clicked.connect(self.char_list_refresh)
        self.top_bar_layout.addWidget(refreshButton)

        # Top Bar
        #
        ################################################################################################################

        # Scroll Panel
        self.scroll_panel = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_panel)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_panel)
        self.main_layout.addWidget(self.scroll_area)

        self.mainTab = MainTab( **data )
        self.libTab  = LibTab(  **data )

        # Tab Layout
        qtab = QTabWidget()

        qtab.addTab( self.mainTab, "Main"    )
        qtab.addTab( self.libTab,  "Library" )

        self.scroll_layout.addWidget(qtab)

        self.setObjectName( self.ui_name )

        if restore:
            mixinPtr = omui.MQtUtil.findControl( customMixinWindow.objectName() )
            omui.MQtUtil.addWidgetToMayaLayout( long(mixinPtr), long(restoredControl) )
        else:
            self.show(dockable=True, height=600, width=480, uiScript='AniMetaUIUIScript(restore=True)')

    # Rename the active character
    def menu_rename(self):

        active_char = self.get_active_char()

        if active_char:
            result = mc.promptDialog(
                text=active_char,
                message='New Name:',
                button=['OK', 'Cancel'],
                defaultButton='OK',
                cancelButton='Cancel',
                dismissString='Cancel',
                title='Rename Character'
            )

            if result == 'OK':
                new_name = mc.promptDialog(query=True, text=True)

                mc.rename( active_char, new_name )

                self.char_list_refresh()

        else:
            mc.warning( 'aniMeta: No character to rename.')
            self.char_list_refresh()

    # Duplicate the active character
    def menu_duplicate(self):

        active_char = self.get_active_char()

        if active_char:
            if mc.objExists( active_char ):
                new_char = mc.duplicate( active_char, rr=True, un=True )[0]

                self.char_list_refresh()

                self.set_active_char( new_char )

        else:
            mc.warning( 'aniMeta: No character to duplicate.')
            self.char_list_refresh()

    # Delete the active character
    def menu_delete(self):

        active_char = self.get_active_char()

        if active_char:
            result = mc.confirmDialog(
                title='Delete Character',
                message='Delete {0}?'.format(active_char),
                button=['Yes','No'],
                defaultButton='Yes',
                cancelButton='No',
                dismissString='No'
            )
            if result == 'Yes':

                am = AniMeta()

                # Delete the HumanIK definition first or it will stick around in the scene
                Char().delete_mocap()

                if mc.objExists( active_char ):
                    mc.delete( active_char )
        else:
            mc.warning( 'aniMeta: No character to delete.')

        self.char_list_refresh()
        self.ui_refresh()

    # Select the active character
    def menu_select(self):

        active_char = self.get_active_char()

        if active_char:
            if mc.objExists( active_char ):
                mc.select( active_char, r=True )
        else:
            mc.warning( 'aniMeta: No character to select.')
            self.char_list_refresh()

    def ui_refresh( self, *args ):
        ptr = omui.MQtUtil.findControl('aniMetaUI')
        widget = wrapInstance(long(ptr), QWidget)
        ui = AniMetaUI(widget)
        ui.mainTab.ui_update()

    def ui_delete( self, *args ):
        try:
            self.close()
        except:
            pass

    def set_active_char( self, character ):
        self.char_list_refresh()
        char_list = self.get_char_list()
        index = char_list.findText(character)
        if index != -1:
            char_list.setCurrentIndex(index)
        else:
            mc.warning('aniMeta: Can not find character', character)

class FrameWidget( QGroupBox ):
 

    def __init__(self, title='', parent=None):
        super(FrameWidget, self).__init__(title, parent)

        self.set_frame_proportions()  # prepare frame_height, text-offset, triangle-points
        self.setContentsMargins( px(4), self.frame_height, px(4), px(0))  # <- using frame_height

        layout =  QVBoxLayout()
        layout.setContentsMargins( 0, 0, 0, 0)
        layout.setSpacing(0)

        super(FrameWidget, self).setLayout(layout)

        self.__widget =  QFrame(parent)

        self.__widget.setFrameShape( QFrame.Panel)
        self.__widget.setFrameShadow( QFrame.Plain)
        self.__widget.setLineWidth(0)

        layout.addWidget(self.__widget)

        self.__collapsed = False

        self.__widget.setAutoFillBackground(True)
        pal = self.__widget.palette()
        pal.setColor(QPalette.Window, QColor(73,73,73)) 
        self.__widget.setPalette(pal)
 

    def setLayout(self, layout):
        self.__widget.setLayout(layout)

    def expandCollapseRect(self):
        return  QRect(0, 0, self.width(), self.frame_height)

    def mouseReleaseEvent(self, event):
        if self.expandCollapseRect().contains(event.pos()):
            self.toggleCollapsed()
            event.accept()
        else:
            event.ignore()

    def toggleCollapsed(self):
        self.setCollapsed(not self.__collapsed)

    def setCollapsed(self, state=True):
        self.__collapsed = state

        if state: 
            self.__widget.setVisible(False)
        else: 
            self.__widget.setVisible(True)

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)

        font = painter.font()
        font.setWeight(QFont.Bold) # font.setBold(True)
        painter.setFont(font)

        painter.setRenderHint(QPainter.Antialiasing)

        currentBrush = painter.brush()
        currentPen   = painter.pen()
        
        # 1. draw background-rectang with tiny radius
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QBrush(QColor(93, 93, 93), QtCore.Qt.SolidPattern)) 
        painter.drawRoundedRect(self.expandCollapseRect(), 1.5,1.5)  

        # 2. draw triangle
        painter.setBrush( QBrush( QColor(238, 238, 238), Qt.SolidPattern ) ) 
        self.__drawTriangle(painter)  

        # 3. draw text 
        painter.setPen(currentPen)
        painter.setBrush(currentBrush)

        painter.drawText(
            self.text_offset, 0, self.width()-self.text_offset, self.frame_height,
            Qt.AlignLeft | Qt.AlignVCenter, 
            self.title()
            )
        painter.end()

    def __drawTriangle(self, painter, x, y):
 
        if self.__collapsed:
            points = self.points_collapsed
        else:
            points = self.points_open

        painter.setRenderHint( QPainter.Antialiasing, False)
        painter.drawPolygon( QPolygon( points ) )
        painter.setRenderHint( QPainter.Antialiasing)

    def __drawTriangle(self, painter): # , x, y
        
        # set point list
        if self.__collapsed:
            points = self.points_collapsed
        else:
            points = self.points_open

        painter.setRenderHint( QPainter.Antialiasing, False)
        painter.drawPolygon( QPolygon( points ) )
        painter.setRenderHint( QPainter.Antialiasing)

    def set_frame_proportions(self):
        # <------------------------------------------>
        # depending on maya's dpi-scaling (real_scale)
        # cmds.FrameLayout has:
        # - nonLinear height-values
        # - nonLinear placement and size of the triangle
        # - nonLinear TextOffset
        # exception: triangle of 125% version has same size as 100%-triangle
        self.frame_height = 22;self.text_offset=38   # 100%
        pnts_open = ((10,6), (19,6), (14.5,11));pnts_collapsed = ((12,4), (12,14), (17,8.5))
        
        # maya_custom_scale_variations:
        if real_scale == 1.25:                      # 125%
            self.frame_height = 24;self.text_offset=40;so=1.0
            pnts_open = ((11,7), (20,7), (15.5,12));pnts_collapsed = ((13,5), (13,15), (18,9.5))
        elif real_scale == 1.5:                     # 150%
            self.frame_height = 28;self.text_offset=44
            pnts_open = ((11,8), (24,8), (17.5,15));pnts_collapsed = ((14,5), (14,19), (21,11.5))
        elif real_scale == 2.0:                     # 200%
            self.frame_height = 37;self.text_offset=53
            pnts_open = ((12,12), (33,12), (22.5,22));pnts_collapsed = ((18,7), (18,26), (28,16.5))
        # <------------------------------------------>
        
        self.points_open =      [ QPoint( pnts_open[0][0], pnts_open[0][1]),
                                  QPoint( pnts_open[1][0], pnts_open[1][1]),
                                  QPoint( pnts_open[2][0], pnts_open[2][1]) ]
        
        self.points_collapsed = [ QPoint( pnts_collapsed[0][0], pnts_collapsed[0][1]),
                                  QPoint( pnts_collapsed[1][0], pnts_collapsed[1][1]),
                                  QPoint( pnts_collapsed[2][0], pnts_collapsed[2][1]) ]


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent):
        # Ignore all wheel events (no change in value)
        event.ignore()

class MainTab( QWidget ):

    def __init__(self, *argv, **keywords):

        super(MainTab, self).__init__( )

        self.charList = None
        self.am       = AniMeta()
        self.rig      = Rig()

        if 'charList' in keywords:
            self.charList = keywords['charList']

        self.char        = None
        self.char_save   = None
        self.char_load   = None
        self.mode_toggle = None

        # Picker
        self.__options__()

        self.button_spacing = 0
        self.picker_rows    = 32
        self.picker_height  = self.button_size * self.picker_rows
        self.maya_blue      = '#5285A6'
        self.blue           = '#6785A6'
        self.red            = '#A65252'
        self.yellow         = '#DBC472'
        self.orange         = '#DF6E41'
        self.grey           = '#777777'
        self.grey_light     = '#777777'

        self.style_active = 'QPushButton{ background-color: ' + self.maya_blue + '; color: #ffffff }'
        self.style_not_active = 'QPushButton{ background-color: ' + self.grey + '; color: #ffffff }'

        # Temp Pose for Copy/Paste
        self.pose           = None

        self.__ui__()

    def __options__( self ):

        self.button_sizes   = { 'X-Small': px(16), 'Small': px(20), 'Medium': px(24), 'Large': px(28), 'X-Large': px(32) }
        self.button_sizes_names = ( 'X-Small', 'Small', 'Medium', 'Large', 'X-Large' )
        if not mc.optionVar( exists = 'aniMetaUIButtonSize' ):
            mc.optionVar( sv = [ 'aniMetaUIButtonSize', 'Medium' ] )

        button_size_string = mc.optionVar( query = 'aniMetaUIButtonSize' )

        if button_size_string in self.button_sizes:
            self.button_size = self.button_sizes[button_size_string]
        else:
            self.button_size = self.button_sizes['Medium']

    def get_button_options ( self ):
        return self.button_sizes_names

    def guides_mode( self ):

        Char().toggle_guides()
        self.pickerWidget.setEnabled( False )

    def controls_mode( self ):

        Char().toggle_guides()
        self.pickerWidget.setEnabled( True )


    def __ui__( self ):

        frames_layout = QVBoxLayout( self )
        frames_layout.setSpacing(2) 

        self.setLayout(frames_layout)

        self.leg_mode_L = kIK
        self.leg_mode_R = kIK

        self.arm_mode_L = kFK
        self.arm_mode_R = kFK

        ########################################
        #   Create
 
        frame1 = FrameWidget('Create', None   )
        frames_layout.addWidget(frame1)

        widget = QWidget(frame1)
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        frame1.setLayout(layout)

        createButton = QPushButton("Create New Character", self)
        createButton.setStyleSheet(
            "QPushButton { background-color: "+self.orange+";  }"
            "QPushButton:hover {  border: 1px solid #dddddd;}"
            "QPushButton:pressed { background-color: white; }"
        )
        layout.addWidget(createButton)

        createButton.clicked.connect( partial( Char().create, name = 'Eve', type = kBipedUE  ))

        #   Create
        ########################################

        ########################################
        #   Edit

        frame1 = FrameWidget('Edit', None  )
        frames_layout.addWidget(frame1)

        widget   = QWidget(frame1)
        layoutV  = QVBoxLayout(widget)
        layoutV.setSpacing(px(2))
        layoutV.setContentsMargins( px(8), px(12), px(8), px(12) )

        layoutH  = QHBoxLayout(self)
        layoutH.setSpacing(px(2))

        layoutV.addLayout(layoutH)
        frame1.setLayout(layoutV)

        self.modeLabel = QLabel("Rig Mode", self)

        self.modeGuides = QPushButton("Guide", self)
        self.modeGuides.clicked.connect( self.guides_mode )

        self.modeControls = QPushButton("Control", self)
        self.modeControls.clicked.connect(  self.controls_mode )

        layoutH.addWidget( self.modeLabel )
        layoutH.addWidget( self.modeGuides )
        layoutH.addWidget( self.modeControls )

        layoutH2  = QHBoxLayout(self)
        layoutH2.setSpacing(px(2))
        layoutV.addLayout(layoutH2)

        self.lockGuides1 = QPushButton( "Lock Guides", self )
        self.lockGuides2 = QPushButton(  "Del Lock", self )
        self.lockGuides3 = QPushButton("Del All Locks", self )

        self.lockGuides1.clicked.connect( self.guide_lock_create )
        self.lockGuides2.clicked.connect( self.guide_lock_delete )
        self.lockGuides3.clicked.connect( partial( self.guide_lock_delete, all=True ))

        layoutH2.addWidget( self.lockGuides1 )
        layoutH2.addWidget( self.lockGuides2 )
        layoutH2.addWidget( self.lockGuides3 )

        #   Edit
        ########################################

        ########################################
        #   Options

        frame1 = FrameWidget('General Options', None  )
        frames_layout.addWidget( frame1 )

        widget = QWidget( frame1 )
        layout = QVBoxLayout( widget )
        layout.setSpacing( 0 )
        layout.setContentsMargins( px(8), px(4), px(8), px(4) )
        frame1.setLayout(layout)

        self.showChar = QCheckBox( "Show Character", self )
        self.showChar.setTristate( False )
        self.showChar.clicked.connect( self.show_character )
        layout.addWidget( self.showChar )

        self.showRig = QCheckBox( "Show Control Rig", self )
        self.showRig.clicked.connect( self.show_rig)
        layout.addWidget( self.showRig )

        self.showGuides = QCheckBox( "Show Guides", self )
        self.showGuides.clicked.connect( self.show_guides )
        layout.addWidget( self.showGuides )

        self.showGeo = QCheckBox( "Show Geometry", self )
        self.showGeo.clicked.connect( self.show_geo)
        layout.addWidget( self.showGeo )

        self.showJoints = QCheckBox( "Show Joints", self )
        self.showJoints.clicked.connect( self.show_joints )
        layout.addWidget( self.showJoints )

        self.showMocap = QCheckBox( "Show Mocap", self )
        self.showMocap.clicked.connect( self.show_mocap )
        layout.addWidget( self.showMocap )

        self.showUpVecs = QCheckBox("Show Up Vectors", self )
        self.showUpVecs.clicked.connect(self.show_upVecs)
        layout.addWidget( self.showUpVecs )

        # Joint Display Type
        line = QHBoxLayout()
        layout.addLayout( line )

        text = QLabel( 'Joint Display Type')
        self.jointMode = QComboBox( self)
        self.jointMode.insertItem( 0, 'Normal' )
        self.jointMode.insertItem( 1, 'Template' )
        self.jointMode.insertItem( 2, 'Reference' )
        line.addWidget(text)
        line.addWidget(self.jointMode)
        self.jointMode.currentIndexChanged.connect( self.set_joint_display )

        # Geo Display Type
        line = QHBoxLayout()
        layout.addLayout( line )

        text = QLabel( 'Geo Display Type')
        self.geoMode = QComboBox( self)
        self.geoMode.insertItem( 0, 'Normal' )
        self.geoMode.insertItem( 1, 'Template' )
        self.geoMode.insertItem( 2, 'Reference' )
        line.addWidget(text)
        line.addWidget(self.geoMode)
        self.geoMode.currentIndexChanged.connect( self.set_geo_display )

        # Global Scale
        line = QHBoxLayout()
        layout.addLayout( line )

        text = QLabel( 'Global Scale')
        self.globalScale = NoWheelDoubleSpinBox ( )
        self.globalScale.setValue( 1.0 )
        self.globalScale.setSingleStep( 0.1 )
        self.globalScale.setMinimum( 0.0001 )
        self.globalScale.setMaximum( 100.0 )
        self.globalScale.valueChanged[float].connect( self.set_global_scale )

        def wheelEvent(self, event: QWheelEvent):
            # Ignore all wheel events (no change in value)
            event.ignore()

        line.addWidget(text)
        line.addWidget(self.globalScale)

        # Control Scale
        line = QHBoxLayout()
        layout.addLayout( line )

        text = QLabel( 'Control Scale')
        self.ctrlScale = NoWheelDoubleSpinBox ( )
        self.ctrlScale.setValue( 1.0 )
        self.ctrlScale.setSingleStep( 0.1 )
        self.ctrlScale.setMinimum( 0.0001 )
        self.ctrlScale.setMaximum( 100.0 )
        self.ctrlScale.valueChanged[float].connect( self.set_ctrl_scale )
        line.addWidget(text)
        line.addWidget(self.ctrlScale)

        # Joint Radius
        line = QHBoxLayout()
        layout.addLayout( line )

        text = QLabel( 'Joint Radius')
        self.jointRadius = NoWheelDoubleSpinBox ( )
        self.jointRadius.setValue( 1.0 )
        self.jointRadius.setSingleStep( 0.1 )
        self.jointRadius.setMinimum( 0.0001 )
        self.jointRadius.setMaximum( 100.0 )
        self.jointRadius.valueChanged[float].connect( self.set_joint_radius )
        line.addWidget(text)
        line.addWidget(self.jointRadius)

        #   Edit
        ########################################

        frame1 = FrameWidget('Picker', None  )
        frames_layout.addWidget(frame1)
        widget = QWidget(frame1)
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        frame1.setLayout(layout)

        # Picker
        self.picker_create( layout )

        frames_layout.addStretch()

        self.ui_update()

    def button_create(self, *args, **kwargs):

        layout = args[0]
        cell_y = args[1]
        cell_x = args[2]
        color  = args[3]
        row_span = 1
        col_span = 1

        if len( args ) == 6:
            row_span = args[4]
            col_span = args[5]

        button = QPushButton(self)
        button.setFixedSize( self.button_size, self.button_size )
        button.setStyleSheet(
            "QPushButton { background-color: "+color+"; border-radius: 4px; margin: 2px;font-size:12px; }"
            "QPushButton:hover {  border: 1px solid #dddddd;}"
            "QPushButton:pressed { background-color: white; }"
        )
        layout.addWidget( button, cell_y, cell_x, row_span, col_span, Qt.AlignCenter )
        return button

    def copy_pose( self ):

        self.pose = self.rig.get_pose()

    def paste_pose( self ):

        self.rig.set_pose( self.pose )

    def dummy_create(self, *args, **kwargs):

        layout = args[0]
        cell_y = args[1]
        cell_x = args[2]

        row_span = 1
        col_span = 1

        if len( args ) == 6:
            row_span = args[4]
            col_span = args[5]

        button = QPushButton(self)
        button.setFixedSize( self.button_size, self.button_size )
        button.setStyleSheet(
            "QPushButton { background: transparent; border-radius: 4px; padding: 6px; margin: 2px  }"
        )
        button.setEnabled( False )
        layout.addWidget( button, cell_y, cell_x, row_span, col_span, Qt.AlignCenter )
        return button

    def get_state( self, mode ):
        if mode == False:
            return QtCore.Qt.Checked.Unchecked
        if mode == True:
            return QtCore.Qt.Checked.Checked

    def guide_lock_create(self):
        rig   = Rig()
        sel   = mc.ls( sl=True )
        char  = rig.get_active_char()
        nodes = rig.get_nodes(char, { 'Type': kBodyGuide } )

        for s in sel:

            short = rig.short_name(s)

            if short in nodes:

                parent = mc.listRelatives(s, p=True, pa=True) or []

                if parent:
                    m = rig.get_matrix( parent[0] )
                    loc = mc.spaceLocator( name=AniMeta().short_name( s )  + '_Lock' )[0]
                    rig.set_matrix( loc, m)
                    size = mc.getAttr(s + '.controlSize')
                    mc.setAttr(loc + '.localScale', size, size, size)
                    mc.setAttr(loc + '.overrideEnabled', True)
                    mc.setAttr(loc + '.overrideRGBColors', 1)
                    mc.setAttr(loc + '.overrideColorRGB', 1, 0, 0)

                    rig.lock_trs(loc, True)
                    rig.lock_trs(parent[0], False)

                    mc.parentConstraint(loc, parent[0])
                    guides_grp = rig.find_node(char, 'Guides_Grp')

                    rig.set_metaData(loc, {'Type': kBodyGuideLock})
                    mc.parent(loc, guides_grp)
            else:
                mc.warning('aniMeta Create Guide Lock: can not lock node', short, ', only guides can be locked.')
        mc.select( sel, r=True )

    def guide_lock_delete(self, all=False):
        rig = Rig()
        sel = mc.ls(sl=True) or []
        char = rig.get_active_char()
        nodes = rig.get_nodes(char, {'Type': kBodyGuideLock})

        if all:
            sel = nodes
        if len(sel):
            for s in sel:
                short = rig.short_name(s)
                if short in nodes:
                    m = rig.get_matrix( s )
                    con = mc.listConnections( s + '.t', s=True, type='parentConstraint') or []

                    if len(con):
                        con2 = mc.listConnections( con[0] + '.constraintTranslateX', d=True ) or []

                        if len(con2):
                            mc.delete( con[0], s )
                            rig.set_matrix( con2[0], m )
                            rig.lock_trs(con2[0], True )
    def set_style( self, widget, type='Button' ):

        if type == 'Button':
            widget.setStyleSheet(
                "QPushButton { background-color: #555555;  }"
                "QPushButton:hover {  background-color: #777777;  }"
                "QPushButton:pressed { background-color: #666666; }"
            )

    def show_context_menu(self, QPos):

        button = self.sender()

        parent_pos = button.mapToGlobal( QPoint(0, 0) )
        menuPosition = parent_pos + QPos

        self.ctxMenu.clear()

        if button._name in ['Head_Ctr_Ctrl', 'ArmUp_FK_Lft_Ctrl', 'ArmUp_FK_Rgt_Ctrl' ]:
            self.switch_orient_ctx_menu( button._name )

        if button._name in ['Hand_IK_Lft_Ctrl', 'Hand_IK_Rgt_Ctrl', 'Foot_IK_Rgt_Ctrl', 'Foot_IK_Lft_Ctrl'  ]:
            self.switch_space_ctx_menu( button._name )

        self.ctxMenu.move(menuPosition)
        self.ctxMenu.show()

    def switch_orient_ctx_menu(self, name):

        char = self.am.get_active_char()
        node_path = self.am.find_node( char, name )

        state = mc.getAttr( node_path + '.worldOrient')

        rig = Rig()

        self.actionWO = QAction(self, triggered=partial( rig.switch_world_orient, name, True))
        self.actionWO.setText("World Orient")
        self.actionWO.setCheckable(True)

        self.actionLO = QAction(self, triggered=partial( rig.switch_world_orient, name, False))
        self.actionLO.setText("Local Orient")
        self.actionLO.setCheckable(True)

        self.headWOGroup = QActionGroup(self)
        self.headWOGroup.setExclusive(True)
        self.actionLO.setActionGroup(self.headWOGroup)
        self.actionWO.setActionGroup(self.headWOGroup)

        self.ctxMenu.addAction(self.actionLO)
        self.ctxMenu.addAction(self.actionWO)

        if state == 1:
            self.actionWO.setChecked(True)
        else:
            self.actionLO.setChecked(True)

    def switch_space_ctx_menu(self, name):

        char = self.am.get_active_char()
        node_path = self.am.find_node( char, name )

        rig = Rig()

        state = mc.getAttr( node_path + '.space')

        space_names = mc.addAttr( node_path + '.space', q=True, enumName=True)
        space_names = space_names.split(':')

        space_actions = []

        self.handIkGroup = QActionGroup(self)
        self.handIkGroup.setExclusive(True)

        for i in range( len(space_names)):
            action = QAction( self, triggered=partial( rig.switch_space, name, i ) )
            action.setText( space_names[i] )
            action.setCheckable( True )
            action.setActionGroup( self.handIkGroup )
            self.ctxMenu.addAction(action)
            space_actions.append( action )

        space_actions[state].setChecked(True)

    def picker_create(self, mainLayout):

        # Context Menu
        self.ctxMenu = QMenu(self)

        self.pickerWidget = QWidget(self)
        self.pickerLayout = QGridLayout( self.pickerWidget )
        self.pickerLayout.setSpacing(0)
        self.pickerLayout.setAlignment( Qt.AlignCenter )
        self.pickerLayout.setContentsMargins(0,0,0,0)

        two_units   = self.button_size*2
        three_units = self.button_size*3
        four_units  = self.button_size*4
        five_units  = self.button_size*5
        six_units   = self.button_size*6

        ##############################################################
        # Limbs

        self.button_Spine = self.button_create(self.pickerLayout, 8, 6, self.blue, 6, 3)
        self.button_Spine.setFixedSize(three_units, six_units )
        self.button_Spine.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Arm FK L
        self.button_Arm_FK_L = self.button_create( self.pickerLayout, 8, 9, self.blue, 5, 2 )
        self.button_Arm_FK_L.setFixedSize( two_units, five_units )
        self.button_Arm_FK_L.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )


        # Arm FK R
        self.button_Arm_FK_R = self.button_create( self.pickerLayout, 8, 4, self.red, 5, 2 )
        self.button_Arm_FK_R.setFixedSize( two_units, five_units )
        self.button_Arm_FK_R.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Arm IK L
        self.button_Arm_IK_L = self.button_create( self.pickerLayout, 8, 9, self.blue, 5, 2 )
        self.button_Arm_IK_L.setFixedSize( two_units, five_units )
        self.button_Arm_IK_L.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Arm IK R
        self.button_Arm_IK_R = self.button_create( self.pickerLayout, 8, 4, self.red, 5, 2 )
        self.button_Arm_IK_R.setFixedSize( two_units, five_units )
        self.button_Arm_IK_R.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Leg IK R
        self.button_Leg_IK_R = self.button_create(self.pickerLayout, 14, 4, self.blue, 6, 3 )
        self.button_Leg_IK_R.setFixedSize( three_units, six_units )
        self.button_Leg_IK_R.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Leg FK R
        self.button_Leg_FK_R = self.button_create(self.pickerLayout, 14, 4, self.blue, 6, 3 )
        self.button_Leg_FK_R.setFixedSize( three_units, six_units  )
        self.button_Leg_FK_R.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        # Leg IK L
        self.button_Leg_IK_L = self.button_create(self.pickerLayout, 14, 8, self.blue, 6, 3)
        self.button_Leg_IK_L.setFixedSize(three_units, six_units )
        self.button_Leg_IK_L.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        # Leg FK L
        self.button_Leg_FK_L = self.button_create(self.pickerLayout, 14, 8, self.blue, 6, 3)
        self.button_Leg_FK_L.setFixedSize(three_units, six_units )
        self.button_Leg_FK_L.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Head
        self.button_Caput  = self.button_create( self.pickerLayout, 4, 6, self.blue, 4, 3 )
        self.button_Caput.setFixedSize( three_units, four_units   )
        self.button_Caput.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        # Limbs
        ##############################################################

        self.button_sel_all    = self.button_create( self.pickerLayout, 32, 3, self.grey, 1, 9 )
        self.button_sel_all.setFixedWidth( 9*self.button_size )
        self.button_sel_all.setText('Sel All')
        self.button_sel_all.clicked.connect(partial( self.rig.get_handles, mode='select', side=kAll))

        self.button_sel_r    = self.button_create( self.pickerLayout, 33, 3, self.red, 1, 3 )
        self.button_sel_r.setFixedWidth( three_units )
        self.button_sel_r.setText('Sel Rgt')
        self.button_sel_r.clicked.connect( partial ( self.rig.get_handles, mode='select', side=kRight ) )

        self.button_sel_c    = self.button_create( self.pickerLayout, 33, 6, self.grey, 1, 3 )
        self.button_sel_c.setFixedWidth( three_units )
        self.button_sel_c.setText('Sel Ctr')
        self.button_sel_c.clicked.connect( partial ( self.rig.get_handles, mode='select', side=kCenter ) )

        self.button_sel_l    = self.button_create( self.pickerLayout, 33, 9, self.blue, 1, 3 )
        self.button_sel_l.setFixedWidth( three_units )
        self.button_sel_l.setText('Sel Lft')
        self.button_sel_l.clicked.connect( partial ( self.rig.get_handles, mode='select', side=kLeft ) )

        text = QLabel('Mirror')
        self.pickerLayout.addWidget( text, 34, 1, 1, 3)

        text = QLabel('Mirror')
        self.pickerLayout.addWidget( text, 34, 11, 1, 3)

        text = QLabel('Swap')
        self.pickerLayout.addWidget( text, 34, 6, 1, 3)

        self.dummy_create( self.pickerLayout, 3, 0,  self.grey, 1, 1 )
        self.dummy_create( self.pickerLayout, 31, 0,  self.grey, 1, 1 )
        self.dummy_create( self.pickerLayout, 34, 0,  self.grey, 1, 1 )

        self.button_mirrorR_all    = self.button_create( self.pickerLayout, 35, 1, self.grey, 1, 3 )
        self.button_mirrorR_all.setFixedWidth( three_units )
        self.button_mirrorR_all.setText('All >>')
        self.button_mirrorR_all.clicked.connect( partial ( self.rig.swap_pose, mode='all', symMode='mirror',symDir='rightToLeft' ) )
        self.set_style( self.button_mirrorR_all )

        self.button_mirrorR_sel    = self.button_create( self.pickerLayout, 36, 1, self.grey, 1, 3 )
        self.button_mirrorR_sel.setFixedWidth( three_units )
        self.button_mirrorR_sel.setText(' Sel >>')
        self.button_mirrorR_sel.clicked.connect( partial ( self.rig.swap_pose, mode='sel', symMode='mirror',symDir='rightToLeft' ) )
        self.set_style( self.button_mirrorR_sel )

        self.button_mirrorL_all = self.button_create(self.pickerLayout, 35, 11, self.grey, 1, 3)
        self.button_mirrorL_all.setFixedWidth(three_units)
        self.button_mirrorL_all.setText('<< All')
        self.button_mirrorL_all.clicked.connect( partial ( self.rig.swap_pose, mode='all', symMode='mirror',symDir='leftToRight' ) )
        self.set_style( self.button_mirrorL_all )

        self.button_mirrorL_sel = self.button_create(self.pickerLayout, 36, 11, self.grey, 1, 3)
        self.button_mirrorL_sel.setFixedWidth(three_units)
        self.button_mirrorL_sel.setText('<< Sel')
        self.button_mirrorL_sel.clicked.connect( partial ( self.rig.swap_pose, mode='sel', symMode='mirror',symDir='leftToRight' ) )
        self.set_style( self.button_mirrorL_sel )


        self.button_swap_all = self.button_create(self.pickerLayout, 35, 6, self.grey, 1, 3)
        self.button_swap_all.setFixedWidth(three_units)
        self.button_swap_all.setText('<< All >>')
        self.button_swap_all.clicked.connect( partial ( self.rig.swap_pose, mode='all', symMode='swap'  ) )
        self.set_style( self.button_swap_all )

        self.button_swap_sel = self.button_create(self.pickerLayout, 36, 6, self.grey, 1, 3)
        self.button_swap_sel.setFixedWidth(three_units)
        self.button_swap_sel.setText('<< Sel >>')
        self.button_swap_sel.clicked.connect( partial ( self.rig.swap_pose, mode='sel', symMode='swap'  ) )
        self.set_style( self.button_swap_sel )

        self.button_reset_all    = self.button_create( self.pickerLayout, 4, 11,  self.grey, 1, 3 )
        self.button_reset_all.setFixedWidth( three_units )
        self.button_reset_all.setText('Reset All')
        self.button_reset_all.clicked.connect( partial ( self.rig.get_handles, mode='reset', side=kAll ) )
        self.set_style( self.button_reset_all )

        self.button_reset_sel    = self.button_create( self.pickerLayout, 5, 11,  self.grey, 1, 3 )
        self.button_reset_sel.setFixedWidth( three_units )
        self.button_reset_sel.setText('Reset Sel')
        self.button_reset_sel.clicked.connect( partial ( self.rig.get_handles, mode='reset', side=kSelection ) )
        self.set_style( self.button_reset_sel )

        self.button_key_all    = self.button_create( self.pickerLayout, 4, 1,  self.red, 1, 3 )
        self.button_key_all.setFixedWidth( three_units )
        self.button_key_all.setText('Key All')
        self.button_key_all.clicked.connect( partial ( self.rig.get_handles, mode='key', side=kAll ) )
        self.set_style( self.button_key_all )

        self.button_key_sel    = self.button_create( self.pickerLayout, 5, 1,  self.red, 1, 3 )
        self.button_key_sel.setFixedWidth( three_units )
        self.button_key_sel.setText('Key Sel')
        self.button_key_sel.clicked.connect( partial ( self.rig.get_handles, mode='key', side=kSelection ) )
        self.set_style( self.button_key_sel )

        self.button_pose_copy = self.button_create( self.pickerLayout, 39, 1,  self.red, 1, 5 )
        self.button_pose_copy.setFixedWidth( five_units )
        self.button_pose_copy.setText('Copy Pose')
        self.set_style( self.button_pose_copy )
        self.button_pose_copy.clicked.connect(  self.copy_pose )

        self.button_pose_paste = self.button_create( self.pickerLayout, 39, 9,  self.red, 1, 5 )
        self.button_pose_paste.setFixedWidth( five_units )
        self.button_pose_paste.setText('Paste Pose')
        self.set_style( self.button_pose_paste )
        self.button_pose_paste.clicked.connect(  self.paste_pose )

        ########################################################################################################
        # IK

        # Leg IK Switch R
        self.button_ik_arm_switch_R   = self.button_create( self.pickerLayout, 8, 1, self.red, 1, 3 )
        self.button_ik_arm_switch_R.setFixedWidth(  three_units )
        self.button_ik_arm_switch_R.setText('IK <> FK')
        self.button_ik_arm_switch_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_IK_R','Nodes':['Arm_IK_Rgt'], 'Switch': True } ) )

        self.button_ik_arm_R   = self.button_create( self.pickerLayout, 9, 2, self.grey, 1, 1 )
        self.button_ik_arm_R.setFixedWidth( self.button_size )
        self.button_ik_arm_R.setText('IK')
        self.button_ik_arm_R.setStyleSheet('QPushButton{background-color:'+self.red+'; padding: 2px;}')
        self.button_ik_arm_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_IK_R','Nodes':['Arm_IK_Rgt'], 'Switch': False } ) )

        self.button_fk_arm_R = self.button_create( self.pickerLayout, 9, 3, self.grey, 1, 1 )
        self.button_fk_arm_R.setFixedWidth( self.button_size )
        self.button_fk_arm_R.setText('FK')
        self.button_fk_arm_R.setStyleSheet('QPushButton{background-color:#666666; padding: 2px;}')
        self.button_fk_arm_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_FK_R','Nodes':['Arm_IK_Rgt'], 'Switch': False } ) )

        # Leg IK Switch L
        self.button_ik_arm_switch_L   = self.button_create( self.pickerLayout, 8, 11, self.blue, 1, 3 )
        self.button_ik_arm_switch_L.setFixedWidth(  three_units )
        self.button_ik_arm_switch_L.setText('IK <> FK')
        self.button_ik_arm_switch_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_IK_L','Nodes':['Arm_IK_Lft'], 'Switch': True } ) )

        self.button_ik_arm_L = self.button_create( self.pickerLayout, 9, 12, self.grey, 1, 1 )
        self.button_ik_arm_L.setFixedWidth( self.button_size )
        self.button_ik_arm_L.setText('IK')
        self.button_ik_arm_L.setStyleSheet('QPushButton{background-color:'+self.red+'; padding: 2px;}')
        self.button_ik_arm_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_IK_L','Nodes':['Arm_IK_Lft'], 'Switch': False} ) )

        self.button_fk_arm_L = self.button_create( self.pickerLayout, 9, 11, self.grey, 1, 1 )
        self.button_fk_arm_L.setFixedWidth( self.button_size )
        self.button_fk_arm_L.setText('FK')
        self.button_fk_arm_L.setStyleSheet('QPushButton{background-color:#666666; padding: 2px;}')
        self.button_fk_arm_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Arm_FK_L','Nodes':['Arm_IK_Lft'], 'Switch': False} ) )


        # Leg IK Switch R
        self.button_ik_leg_switch_R   = self.button_create( self.pickerLayout, 14, 1, self.red, 1, 3 )
        self.button_ik_leg_switch_R.setFixedWidth(  three_units )
        self.button_ik_leg_switch_R.setText('IK <> FK')
        self.button_ik_leg_switch_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_IK_R','Nodes':['Leg_IK_Rgt'], 'Switch': True } ) )

        self.button_ik_leg_R   = self.button_create( self.pickerLayout, 15, 2, self.grey, 1, 1 )
        self.button_ik_leg_R.setFixedWidth( self.button_size )
        self.button_ik_leg_R.setText('IK')
        self.button_ik_leg_R.setStyleSheet('QPushButton{background-color:'+self.red+'; padding: 2px;}')
        self.button_ik_leg_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_IK_R','Nodes':['Leg_IK_Rgt'], 'Switch': False } ) )

        self.button_fk_leg_R = self.button_create( self.pickerLayout, 15, 3, self.grey, 1, 1 )
        self.button_fk_leg_R.setFixedWidth( self.button_size )
        self.button_fk_leg_R.setText('FK')
        self.button_fk_leg_R.setStyleSheet('QPushButton{background-color:#666666; padding: 2px;}')
        self.button_fk_leg_R.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_FK_R','Nodes':['Leg_IK_Rgt'], 'Switch': False } ) )

        # Leg IK Switch L
        self.button_ik_leg_switch_L   = self.button_create( self.pickerLayout, 14, 11, self.blue, 1, 3 )
        self.button_ik_leg_switch_L.setFixedWidth(  three_units )
        self.button_ik_leg_switch_L.setText('IK <> FK')
        self.button_ik_leg_switch_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_IK_L','Nodes':['Leg_IK_Lft'], 'Switch': True } ) )

        self.button_ik_leg_L = self.button_create( self.pickerLayout, 15, 12, self.grey, 1, 1 )
        self.button_ik_leg_L.setFixedWidth( self.button_size )
        self.button_ik_leg_L.setText('IK')
        self.button_ik_leg_L.setStyleSheet('QPushButton{background-color:'+self.red+'; padding: 2px;}')
        self.button_ik_leg_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_IK_L','Nodes':['Leg_IK_Lft'], 'Switch': False} ) )

        self.button_fk_leg_L = self.button_create( self.pickerLayout, 15, 11, self.grey, 1, 1 )
        self.button_fk_leg_L.setFixedWidth( self.button_size )
        self.button_fk_leg_L.setText('FK')
        self.button_fk_leg_L.setStyleSheet('QPushButton{background-color:#666666; padding: 2px;}')
        self.button_fk_leg_L.clicked.connect( partial ( self.picker_cmd, {'Mode': 'Leg_FK_L','Nodes':['Leg_IK_Lft'], 'Switch': False} ) )

        ############################################################
        # Controls
        self.button_Eyes    = self.button_create( self.pickerLayout, 4, 7, self.yellow )
        self.button_Eye_L    = self.button_create( self.pickerLayout, 4, 8, self.blue )
        self.button_Eye_R    = self.button_create( self.pickerLayout, 4, 6, self.red )

        self.button_Jaw    = self.button_create( self.pickerLayout, 5, 7, self.yellow )


        # Head
        self.button_Head   = self.button_create( self.pickerLayout, 6, 6, self.yellow, 1, 3 )
        self.button_Head.setFixedWidth( three_units )

        # Head Context Menu
        self.button_Head._name = 'Head_Ctr_Ctrl'
        self.button_Head.installEventFilter(self)
        self.button_Head.setContextMenuPolicy( Qt.CustomContextMenu)
        self.button_Head.customContextMenuRequested.connect( self.show_context_menu )
        self.button_Head.setCursor( Qt.WhatsThisCursor ) 
        self.button_Neck   = self.button_create( self.pickerLayout, 7, 7, self.yellow )


        style_grey = "QPushButton { background-color: #777777; border-radius: 4px; padding: 6px; margin: 2px  }"

        # Torso
        self.button_Chest   = self.button_create( self.pickerLayout, 8, 6, self.yellow, 1, 3 )
        self.button_Chest.setFixedWidth( three_units )
        self.button_Chest.setToolTip( 'Chest')

        self.button_Spine4  = self.button_create( self.pickerLayout, 9, 7, self.yellow )
        self.button_Spine3  = self.button_create( self.pickerLayout, 10, 7, self.yellow )
        self.button_Spine2  = self.button_create( self.pickerLayout, 11, 7, self.yellow )
        self.button_Spine1  = self.button_create( self.pickerLayout, 12, 7, self.yellow )
        self.button_Hips    = self.button_create( self.pickerLayout, 13, 7, self.yellow )

        self.button_Torso    = self.button_create( self.pickerLayout, 14, 6, self.yellow, 1, 3 )
        self.button_Torso.setFixedWidth( three_units )
        self.button_Torso.setToolTip( 'Torso')
        self.button_HipsUpVec_L    = self.button_create( self.pickerLayout, 14, 9, self.blue, 1, 1 )
        self.button_HipsUpVec_R    = self.button_create( self.pickerLayout, 14, 5, self.blue, 1, 1 )

        # Arm L
        # FK
        self.button_Clavicle_L = self.button_create( self.pickerLayout, 8, 9, self.blue )
        self.button_ArmUp_L    = self.button_create( self.pickerLayout, 8, 10, self.blue, 2, 1 )
        self.button_ArmUp_L.setFixedHeight( two_units  )
        self.button_ShoulderUpVec_L = self.button_create( self.pickerLayout, 7, 9, self.blue )

        ###################################################################################################
        # Orientation Switch Context Menu

        self.button_ArmUp_L._name = 'ArmUp_FK_Lft_Ctrl'
        self.button_ArmUp_L.installEventFilter(self)
        self.button_ArmUp_L.setContextMenuPolicy( Qt.CustomContextMenu)
        self.button_ArmUp_L.customContextMenuRequested.connect( self.show_context_menu )
        self.button_ArmUp_L.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################

        self.button_ArmLo_L  = self.button_create( self.pickerLayout, 10, 10, self.blue, 2,1 )
        self.button_ArmLo_L.setFixedHeight( two_units )

        self.button_Hand_L   = self.button_create( self.pickerLayout, 12, 10, self.blue )

        # IK
        self.button_Hand_IK_L   = self.button_create( self.pickerLayout, 12, 9, self.blue )

        ###################################################################################################
        # Orientation Switch Context Menu

        self.button_Hand_IK_L._name = 'Hand_IK_Lft_Ctrl'
        self.button_Hand_IK_L.installEventFilter(self)
        self.button_Hand_IK_L.setContextMenuPolicy(Qt.CustomContextMenu)
        self.button_Hand_IK_L.customContextMenuRequested.connect(self.show_context_menu)
        self.button_Hand_IK_L.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################

        self.button_ArmUp_IK_L    = self.button_create( self.pickerLayout, 8, 10, self.grey, 2, 1 )
        self.button_ArmUp_IK_L.setFixedHeight( two_units  )
        self.button_ArmUp_IK_L.setEnabled( False )
        self.button_ArmUp_IK_L.setStyleSheet( style_grey  )

        self.button_ArmLo_IK_L  = self.button_create( self.pickerLayout, 10, 10, self.grey, 2,1 )
        self.button_ArmLo_IK_L.setFixedHeight( two_units )
        self.button_ArmLo_IK_L.setEnabled( False )
        self.button_ArmLo_IK_L.setStyleSheet( style_grey  )

        self.button_ArmPole_IK_L  = self.button_create( self.pickerLayout, 10, 9, self.blue, 1,1 )

        self.buttons_arm_fk_L = [self.button_ArmUp_L, self.button_ArmLo_L, self.button_Arm_FK_L ]
        self.buttons_arm_ik_L = [ self.button_ArmPole_IK_L, self.button_ArmUp_IK_L, self.button_ArmLo_IK_L, self.button_Hand_IK_L, self.button_Arm_IK_L ]

        # Arm R
        # FK
        self.button_Clavicle_R = self.button_create( self.pickerLayout, 8, 5, self.red )
        self.button_ArmUp_R    = self.button_create( self.pickerLayout, 8, 4, self.red, 2, 1 )
        self.button_ArmUp_R.setFixedHeight( two_units )
        self.button_ShoulderUpVec_R = self.button_create( self.pickerLayout, 7, 5, self.red )

        ###################################################################################################
        # Orientation Switch Context Menu

        self.button_ArmUp_R._name = 'ArmUp_FK_Rgt_Ctrl'
        self.button_ArmUp_R.installEventFilter(self)
        self.button_ArmUp_R.setContextMenuPolicy(Qt.CustomContextMenu)
        self.button_ArmUp_R.customContextMenuRequested.connect(self.show_context_menu)
        self.button_ArmUp_R.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################

        self.button_ArmLo_R  = self.button_create( self.pickerLayout, 10, 4, self.red, 2,1 )
        self.button_ArmLo_R.setFixedHeight( two_units )

        self.button_Hand_R   = self.button_create( self.pickerLayout, 12, 4, self.red )



        # IK

        self.button_Hand_IK_R   = self.button_create( self.pickerLayout, 12, 5, self.red )


        ###################################################################################################
        # Space Switch Context Menu

        self.button_Hand_IK_R._name = 'Hand_IK_Rgt_Ctrl'
        self.button_Hand_IK_R.installEventFilter(self)
        self.button_Hand_IK_R.setContextMenuPolicy(Qt.CustomContextMenu)
        self.button_Hand_IK_R.customContextMenuRequested.connect(self.show_context_menu)
        self.button_Hand_IK_R.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################


        self.button_ArmUp_IK_R    = self.button_create( self.pickerLayout, 8, 4, self.grey, 2, 1 )
        self.button_ArmUp_IK_R.setFixedHeight( two_units  )
        self.button_ArmUp_IK_R.setEnabled( False )
        self.button_ArmUp_IK_R.setStyleSheet( style_grey  )

        self.button_ArmLo_IK_R  = self.button_create( self.pickerLayout, 10, 4, self.grey, 2,1 )
        self.button_ArmLo_IK_R.setFixedHeight( two_units )
        self.button_ArmLo_IK_R.setEnabled( False )
        self.button_ArmLo_IK_R.setStyleSheet( style_grey  )

        self.button_ArmPole_IK_R  = self.button_create( self.pickerLayout, 10, 5, self.red, 1,1 )

        self.buttons_arm_fk_R = [self.button_ArmUp_R, self.button_ArmLo_R, self.button_Arm_FK_R  ]
        self.buttons_arm_ik_R = [self.button_ArmPole_IK_R, self.button_ArmUp_IK_R, self.button_ArmLo_IK_R, self.button_Hand_IK_R, self.button_Arm_IK_R ]



        # Leg IK R
        self.button_LegUp_IK_R  = self.button_create( self.pickerLayout, 15, 6, self.red, 2, 1 )
        self.button_LegUp_IK_R.setFixedHeight( two_units )
        self.button_LegUp_IK_R.setEnabled( False )
        self.button_LegUp_IK_R.setStyleSheet( style_grey  )

        self.button_LegLo_IK_R  = self.button_create( self.pickerLayout, 17, 6, self.red, 2, 1 )
        self.button_LegLo_IK_R.setFixedHeight( two_units )
        self.button_LegLo_IK_R.setEnabled( False )
        self.button_LegLo_IK_R.setStyleSheet( style_grey  )

        self.button_Foot_IK_R   = self.button_create( self.pickerLayout, 19, 6, self.red   )


        ###################################################################################################
        # Space Switch Context Menu

        self.button_Foot_IK_R._name = 'Foot_IK_Rgt_Ctrl'
        self.button_Foot_IK_R.installEventFilter(self)
        self.button_Foot_IK_R.setContextMenuPolicy(Qt.CustomContextMenu)
        self.button_Foot_IK_R.customContextMenuRequested.connect( self.show_context_menu )
        self.button_Foot_IK_R.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################


        self.button_Ball_IK_R   = self.button_create( self.pickerLayout, 19, 5, self.red  )
        self.button_Toes_IK_R   = self.button_create( self.pickerLayout, 19, 4, self.red  )
        self.button_LegPole_IK_R   = self.button_create( self.pickerLayout, 17, 5, self.red  )

        self.button_Heel_IK_R   = self.button_create( self.pickerLayout, 20, 6, self.red  )
        self.button_ToesTip_IK_R= self.button_create( self.pickerLayout, 20, 4, self.red  )

        self.buttons_leg_ik_R = [self.button_LegUp_IK_R,
                         self.button_LegLo_IK_R,
                         self.button_Foot_IK_R,
                         self.button_Ball_IK_R,
                         self.button_Toes_IK_R,
                         self.button_LegPole_IK_R,
                         self.button_Heel_IK_R,
                         self.button_ToesTip_IK_R,
                         self.button_Leg_IK_R   ]

        # Leg FK R
        self.button_LegUp_FK_R  = self.button_create( self.pickerLayout, 15, 6, self.red, 2, 1 )
        self.button_LegUp_FK_R.setFixedHeight( two_units )

        self.button_LegLo_FK_R  = self.button_create( self.pickerLayout, 17, 6, self.red, 2, 1 )
        self.button_LegLo_FK_R.setFixedHeight( two_units )

        self.button_Foot_FK_R   = self.button_create( self.pickerLayout, 19, 6, self.red   )
        self.button_Ball_FK_R   = self.button_create( self.pickerLayout, 19, 5, self.red  )
        self.button_Ball_FK_R.setEnabled( False )
        self.button_Ball_FK_R.setStyleSheet( style_grey  )
        self.button_Toes_FK_R   = self.button_create( self.pickerLayout, 19, 4, self.red  )

        self.buttons_leg_fk_R = [ self.button_LegUp_FK_R,
                         self.button_LegLo_FK_R,
                         self.button_Foot_FK_R,
                         self.button_Ball_FK_R,
                         self.button_Leg_FK_R,
                         self.button_Toes_FK_R ]

        # Leg IK L
        self.button_LegUp_IK_L  = self.button_create( self.pickerLayout, 15, 8, self.blue, 2, 1 )
        self.button_LegUp_IK_L.setFixedHeight( two_units )
        self.button_LegUp_IK_L.setEnabled( False )
        self.button_LegUp_IK_L.setStyleSheet( style_grey  )

        self.button_LegLo_IK_L  = self.button_create( self.pickerLayout, 17, 8, self.blue, 2, 1 )
        self.button_LegLo_IK_L.setFixedHeight( two_units )
        self.button_LegLo_IK_L.setEnabled( False )
        self.button_LegLo_IK_L.setStyleSheet( style_grey  )

        self.button_Foot_IK_L   = self.button_create( self.pickerLayout, 19, 8, self.blue   )

        ###################################################################################################
        # Space Switch Context Menu

        self.button_Foot_IK_L._name = 'Foot_IK_Lft_Ctrl'
        self.button_Foot_IK_L.installEventFilter(self)
        self.button_Foot_IK_L.setContextMenuPolicy(Qt.CustomContextMenu)
        self.button_Foot_IK_L.customContextMenuRequested.connect( self.show_context_menu )
        self.button_Foot_IK_L.setCursor( Qt.WhatsThisCursor )

        # Orientation Switch Context Menu
        ###################################################################################################


        self.button_Ball_IK_L   = self.button_create( self.pickerLayout, 19, 9, self.blue  )
        self.button_Toes_IK_L   = self.button_create( self.pickerLayout, 19, 10, self.blue  )
        self.button_LegPole_IK_L   = self.button_create( self.pickerLayout, 17, 9, self.blue  )

        self.button_Heel_IK_L   = self.button_create( self.pickerLayout, 20, 8, self.blue  )
        self.button_ToesTip_IK_L= self.button_create( self.pickerLayout, 20, 10, self.blue  )

        self.button_Root  = self.button_create( self.pickerLayout, 20, 7, self.yellow )
        self.button_Main   = self.button_create( self.pickerLayout,21, 6, self.yellow, 1, 3 )
        self.button_Main.setFixedWidth( three_units )

        self.buttons_leg_ik_L = [self.button_LegUp_IK_L,
                         self.button_LegLo_IK_L,
                         self.button_Foot_IK_L,
                         self.button_Ball_IK_L,
                         self.button_Toes_IK_L,
                         self.button_LegPole_IK_L,
                         self.button_Heel_IK_L,
                         self.button_ToesTip_IK_L,
                         self.button_Leg_IK_L  ]

        # Leg FK L
        self.button_LegUp_FK_L  = self.button_create( self.pickerLayout, 15, 8, self.blue, 2, 1 )
        self.button_LegUp_FK_L.setFixedHeight( two_units )

        self.button_LegLo_FK_L  = self.button_create( self.pickerLayout, 17, 8, self.blue, 2, 1 )
        self.button_LegLo_FK_L.setFixedHeight( two_units )

        self.button_Foot_FK_L   = self.button_create( self.pickerLayout, 19, 8, self.blue   )
        self.button_Ball_FK_L   = self.button_create( self.pickerLayout, 19, 9, self.blue  )
        self.button_Ball_FK_L.setEnabled( False )
        self.button_Ball_FK_L.setStyleSheet( style_grey  )
        self.button_Toes_FK_L   = self.button_create( self.pickerLayout, 19, 10, self.blue  )

        self.buttons_leg_fk_L = [ self.button_LegUp_FK_L,
                         self.button_LegLo_FK_L,
                         self.button_Foot_FK_L,
                         self.button_Ball_FK_L,
                         self.button_Leg_FK_L  ,
                         self.button_Toes_FK_L   ]

        self.button_Root  = self.button_create( self.pickerLayout, 20, 7, self.yellow )
        self.button_Main   = self.button_create( self.pickerLayout,21, 6, self.yellow, 1, 3 )
        self.button_Main.setFixedWidth( three_units )

        # Controls
        ############################################################

        ############################################################
        # Stack

        self.button_Caput.stackUnder( self.button_Eyes )
        self.button_Leg_IK_L.stackUnder(self.button_LegUp_IK_L)
        self.button_Leg_IK_R.stackUnder(self.button_LegUp_IK_R)
        self.button_Leg_FK_L.stackUnder(self.button_LegUp_IK_L)
        self.button_Leg_FK_R.stackUnder(self.button_LegUp_IK_R)
        self.button_Arm_FK_R.stackUnder(self.button_Clavicle_L)
        self.button_Arm_FK_L.stackUnder(self.button_Clavicle_L)
        self.button_Arm_IK_R.stackUnder(self.button_Clavicle_L)
        self.button_Arm_IK_L.stackUnder(self.button_Clavicle_L)
        self.button_Spine.stackUnder(self.button_Chest)

        # Stack
        ############################################################


        ############################################################
        # Commands

        # Torso
        self.button_Torso.clicked.connect( partial( self.picker_cmd,      {'Nodes': ['Torso_Ctr_Ctrl']} ) )
        self.button_HipsUpVec_L.clicked.connect( partial( self.picker_cmd,{'Nodes': ['HipsUpVec_Lft_Ctrl']} ) )
        self.button_HipsUpVec_R.clicked.connect( partial( self.picker_cmd,{'Nodes': ['HipsUpVec_Rgt_Ctrl']} ) )
        self.button_Spine1.clicked.connect( partial( self.picker_cmd,     {'Nodes': ['Spine1_Ctr_Ctrl']} ) )
        self.button_Spine2.clicked.connect( partial( self.picker_cmd,     {'Nodes': ['Spine2_Ctr_Ctrl']} ) )
        self.button_Spine3.clicked.connect( partial( self.picker_cmd,     {'Nodes': ['Spine3_Ctr_Ctrl']} ) )
        self.button_Spine4.clicked.connect( partial( self.picker_cmd,     {'Nodes': ['Spine4_Ctr_Ctrl']} ) )
        self.button_Chest.clicked.connect(partial(self.picker_cmd,        {'Nodes': ['Spine5_Ctr_Ctrl']}))
        self.button_Hips.clicked.connect(partial(self.picker_cmd,         {'Nodes': ['Hips_Ctr_Ctrl']}))
        self.button_Neck.clicked.connect(partial(self.picker_cmd,         {'Nodes': ['Neck_Ctr_Ctrl']}))
        self.button_Head.clicked.connect(partial(self.picker_cmd,         {'Nodes': ['Head_Ctr_Ctrl']}))
        self.button_Eye_L.clicked.connect(partial(self.picker_cmd,        {'Nodes': ['Eye_Lft_Ctrl']}))
        self.button_Eye_R.clicked.connect(partial(self.picker_cmd,        {'Nodes': ['Eye_Rgt_Ctrl']}))
        self.button_Eyes.clicked.connect(partial(self.picker_cmd,         {'Nodes': ['Eyes_Ctr_Ctrl']}))

        # Arm L
        self.button_Clavicle_L.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['Clavicle_Lft_Ctrl']}))
        self.button_ArmUp_L.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['ArmUp_FK_Lft_Ctrl']}))
        self.button_ArmLo_L.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['ArmLo_FK_Lft_Ctrl']}))
        self.button_Hand_L.clicked.connect(partial(self.picker_cmd,       {'Nodes': ['Hand_FK_Lft_Ctrl']}))
        self.button_Hand_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Hand_IK_Lft_Ctrl']}))
        self.button_ArmPole_IK_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['ArmPole_IK_Lft_Ctrl']}))
        self.button_ShoulderUpVec_L.clicked.connect(partial(self.picker_cmd,{'Nodes': ['ShoulderUpVec_Lft_Ctrl']}))

        # Arm R
        self.button_Clavicle_R.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['Clavicle_Rgt_Ctrl']}))
        self.button_ArmUp_R.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['ArmUp_FK_Rgt_Ctrl']}))
        self.button_ArmLo_R.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['ArmLo_FK_Rgt_Ctrl']}))
        self.button_Hand_R.clicked.connect(partial(self.picker_cmd,       {'Nodes': ['Hand_FK_Rgt_Ctrl']}))
        self.button_Hand_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Hand_IK_Rgt_Ctrl']}))
        self.button_ArmPole_IK_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['ArmPole_IK_Rgt_Ctrl']}))
        self.button_ShoulderUpVec_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['ShoulderUpVec_Rgt_Ctrl']}))

        # Leg IK L
        self.button_Foot_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Foot_IK_Lft_Ctrl']}))
        self.button_Ball_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['FootLift_IK_Lft_Ctrl']}))
        self.button_Toes_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Toes_IK_Lft_Ctrl']}))
        self.button_ToesTip_IK_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['ToesTip_IK_Lft_Ctrl']}))
        self.button_Heel_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Heel_IK_Lft_Ctrl']}))
        self.button_LegPole_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['LegPole_IK_Lft_Ctrl']}))

        # Leg FK L
        self.button_LegUp_FK_L.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['LegUp_FK_Lft_Ctrl']}))
        self.button_LegLo_FK_L.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['LegLo_FK_Lft_Ctrl']}))
        self.button_Foot_FK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Foot_FK_Lft_Ctrl']}))
        self.button_Toes_FK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Toes_FK_Lft_Ctrl']}))

        # Leg IK R
        self.button_Foot_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Foot_IK_Rgt_Ctrl']}))
        self.button_Ball_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['FootLift_IK_Rgt_Ctrl']}))
        self.button_Toes_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Toes_IK_Rgt_Ctrl']}))
        self.button_ToesTip_IK_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['ToesTip_IK_Rgt_Ctrl']}))
        self.button_Heel_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Heel_IK_Rgt_Ctrl']}))
        self.button_LegPole_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['LegPole_IK_Rgt_Ctrl']}))

        # Leg FK R
        self.button_LegUp_FK_R.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['LegUp_FK_Rgt_Ctrl']}))
        self.button_LegLo_FK_R.clicked.connect(partial(self.picker_cmd,   {'Nodes': ['LegLo_FK_Rgt_Ctrl']}))
        self.button_Foot_FK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Foot_FK_Rgt_Ctrl']}))
        self.button_Toes_FK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Toes_FK_Rgt_Ctrl']}))

        # Root
        self.button_Root.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['Root_Ctr_Ctrl']}))
        self.button_Main.clicked.connect(partial(self.picker_cmd,      {'Nodes': ['Main_Ctr_Ctrl']}))

        # Limbs
        self.button_Spine.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Torso_Ctr_Ctrl',
                                                                                 'Spine1_Ctr_Ctrl',
                                                                                 'Spine2_Ctr_Ctrl',
                                                                                 'Spine3_Ctr_Ctrl',
                                                                                 'Spine4_Ctr_Ctrl',
                                                                                 'Spine5_Ctr_Ctrl',
                                                                                 'Hips_Ctr_Ctrl'  ]}))

        self.button_Arm_FK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Clavicle_Lft_Ctrl',
                                                                                 'ArmUp_FK_Lft_Ctrl',
                                                                                 'ArmLo_FK_Lft_Ctrl',
                                                                                 'ShoulderUpVec_Lft_Ctrl',
                                                                                 'Hand_FK_Lft_Ctrl' ]}))

        self.button_Arm_FK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Clavicle_Rgt_Ctrl',
                                                                                 'ArmUp_FK_Rgt_Ctrl',
                                                                                 'ArmLo_FK_Rgt_Ctrl',
                                                                                 'ShoulderUpVec_Rgt_Ctrl',
                                                                                 'Hand_FK_Rgt_Ctrl' ]}))

        self.button_Arm_IK_L.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Clavicle_Lft_Ctrl',
                                                                                 'ArmPole_IK_Lft_Ctrl',
                                                                                 'ShoulderUpVec_Lft_Ctrl',
                                                                                 'Hand_IK_Lft_Ctrl' ]}))

        self.button_Arm_IK_R.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Clavicle_Rgt_Ctrl',
                                                                                 'ArmPole_IK_Rgt_Ctrl',
                                                                                 'ShoulderUpVec_Rgt_Ctrl',
                                                                                 'Hand_IK_Rgt_Ctrl' ]}))


        self.button_Caput.clicked.connect(partial(self.picker_cmd,    {'Nodes': ['Head_Ctr_Ctrl',
                                                                                 'Neck_Ctr_Ctrl',
                                                                                 'Eyes_Ctr_Ctrl',
                                                                                 'Eye_Lft_Ctrl',
                                                                                 'Eye_Rgt_Ctrl']}))

        self.button_Leg_IK_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Foot_IK_Lft_Ctrl',
                                                                                 'FootLift_IK_Lft_Ctrl',
                                                                                 'HipsUpVec_Lft_Ctrl',
                                                                                 'Toes_IK_Lft_Ctrl',
                                                                                 'ToesTip_IK_Lft_Ctrl',
                                                                                 'Heel_IK_Lft_Ctrl',
                                                                                 'LegPole_IK_Lft_Ctrl']}))

        self.button_Leg_FK_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Foot_FK_Lft_Ctrl',
                                                                                 'Toes_FK_Lft_Ctrl',
                                                                                 'HipsUpVec_Lft_Ctrl',
                                                                                 'LegUp_FK_Lft_Ctrl',
                                                                                 'LegLo_FK_Lft_Ctrl']}))

        self.button_Leg_IK_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Foot_IK_Rgt_Ctrl',
                                                                                 'FootLift_IK_Rgt_Ctrl',
                                                                                 'HipsUpVec_Rgt_Ctrl',
                                                                                 'Toes_IK_Rgt_Ctrl',
                                                                                 'ToesTip_IK_Rgt_Ctrl',
                                                                                 'Heel_IK_Rgt_Ctrl',
                                                                                 'LegPole_IK_Rgt_Ctrl']}))

        self.button_Leg_FK_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Foot_FK_Rgt_Ctrl',
                                                                                 'Toes_FK_Rgt_Ctrl',
                                                                                 'HipsUpVec_Rgt_Ctrl',
                                                                                 'LegUp_FK_Rgt_Ctrl',
                                                                                 'LegLo_FK_Rgt_Ctrl']}))
        # Commands
        ############################################################

        ############################################################
        # Hands

        self.dummy_create( self.pickerLayout, 22, 1, self.yellow, 1, 1 )
        self.dummy_create( self.pickerLayout, 23, 1, self.yellow, 1, 1 )


        text = QLabel('Finger Rgt')
        self.pickerLayout.addWidget( text, 22, 1, 1, 6)

        self.button_Hand_R = self.button_create(self.pickerLayout, 23, 1, self.blue, 6, 6)
        self.button_Hand_R.setToolTip( 'All Right-Hand Finger Controls')
        self.button_Hand_R.setFixedSize(six_units, six_units )
        self.button_Hand_R.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        text = QLabel('Finger Lft')
        self.pickerLayout.addWidget( text, 22, 8, 1, 6)

        self.button_Hand_L = self.button_create(self.pickerLayout, 23, 8, self.blue, 6, 6)
        self.button_Hand_L.setToolTip( 'All Left-Hand Fingers Controls')
        self.button_Hand_L.setFixedSize(six_units, six_units )
        self.button_Hand_L.setStyleSheet(
            "QPushButton { background-color: #555555; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button_create( self.pickerLayout, 24, 1, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 25, 1, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 26, 1, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 27, 1, self.grey_light, 1, 1 )

        self.button_create( self.pickerLayout, 23, 2, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 3, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 4, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 5, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 6, self.grey_light, 1, 1 )

        self.button2_Finger1_R = self.button_create(self.pickerLayout, 23, 2, self.blue, 4, 1)
        self.button2_Finger1_R.setFixedSize( self.button_size , four_units )
        self.button2_Finger1_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger2_R = self.button_create(self.pickerLayout, 23, 3, self.blue, 4, 1)
        self.button2_Finger2_R.setFixedSize( self.button_size , four_units )
        self.button2_Finger2_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Finger3_R = self.button_create(self.pickerLayout, 23, 4, self.blue, 4, 1)
        self.button2_Finger3_R.setFixedSize( self.button_size, four_units )
        self.button2_Finger3_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Finger4_R = self.button_create(self.pickerLayout, 23, 5, self.blue, 4, 1)
        self.button2_Finger4_R.setFixedSize( self.button_size, four_units )
        self.button2_Finger4_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger5_R = self.button_create(self.pickerLayout, 23, 6, self.blue, 5, 1)
        self.button2_Finger5_R.setFixedSize( self.button_size , five_units )
        self.button2_Finger5_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Digits4_R = self.button_create(self.pickerLayout, 24, 1, self.blue, 1, 5)
        self.button2_Digits4_R.setFixedSize(   five_units, self.button_size)
        self.button2_Digits4_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Digits3_R = self.button_create(self.pickerLayout, 25, 1, self.blue, 1, 5)
        self.button2_Digits3_R.setFixedSize(   five_units, self.button_size)
        self.button2_Digits3_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Digits2_R = self.button_create(self.pickerLayout, 26, 1, self.blue, 1, 5)
        self.button2_Digits2_R.setFixedSize(   five_units, self.button_size)
        self.button2_Digits2_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Digits1_R = self.button_create(self.pickerLayout, 27, 1, self.blue, 1, 5)
        self.button2_Digits1_R.setFixedSize(   five_units, self.button_size)
        self.button2_Digits1_R.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px; padding: 2px; }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button_create( self.pickerLayout, 23, 8, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 9, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 10, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 11, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 23, 12, self.grey_light, 1, 1 )

        self.button_create( self.pickerLayout, 24, 13, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 25, 13, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 26, 13, self.grey_light, 1, 1 )
        self.button_create( self.pickerLayout, 27, 13, self.grey_light, 1, 1 )

        self.button2_Digits4_L = self.button_create(self.pickerLayout, 24, 9, self.blue, 1, 5)
        self.button2_Digits4_L.setFixedSize(   five_units, self.button_size)
        self.button2_Digits4_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Digits3_L = self.button_create(self.pickerLayout, 25, 9, self.blue, 1, 5)
        self.button2_Digits3_L.setFixedSize(   five_units, self.button_size)
        self.button2_Digits3_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Digits2_L = self.button_create(self.pickerLayout, 26, 9, self.blue, 1, 5)
        self.button2_Digits2_L.setFixedSize(   five_units, self.button_size)
        self.button2_Digits2_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Digits1_L = self.button_create(self.pickerLayout, 27, 9, self.blue, 1, 5)
        self.button2_Digits1_L.setFixedSize(   five_units, self.button_size)
        self.button2_Digits1_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button2_Finger5_L = self.button_create(self.pickerLayout, 23, 8, self.blue, 5, 1)
        self.button2_Finger5_L.setFixedSize( self.button_size, five_units )
        self.button2_Finger5_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger4_L = self.button_create(self.pickerLayout, 23, 9, self.blue, 4, 1)
        self.button2_Finger4_L.setFixedSize( self.button_size, four_units )
        self.button2_Finger4_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger3_L = self.button_create(self.pickerLayout, 23, 10, self.blue, 4, 1)
        self.button2_Finger3_L.setFixedSize( self.button_size, four_units )
        self.button2_Finger3_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger2_L = self.button_create(self.pickerLayout, 23, 11, self.blue, 4, 1)
        self.button2_Finger2_L.setFixedSize( self.button_size, four_units )
        self.button2_Finger2_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )
        self.button2_Finger1_L = self.button_create(self.pickerLayout, 23, 12, self.blue, 4, 1)
        self.button2_Finger1_L.setFixedSize( self.button_size, four_units )
        self.button2_Finger1_L.setStyleSheet(
            "QPushButton { background-color: transparent; border-radius: 4px;  }"
            "QPushButton:hover {  border: 2px solid #dddddd;}"
            "QPushButton:pressed { background-color: #666666; }"
        )

        self.button_Finger1_4_R  = self.button_create( self.pickerLayout, 24, 2, self.red, 1, 1 )
        self.button_Finger1_3_R  = self.button_create( self.pickerLayout, 25, 2, self.red, 1, 1 )
        self.button_Finger1_2_R  = self.button_create( self.pickerLayout, 26, 2, self.red, 1, 1 )
        self.button_Finger1_1_R  = self.button_create( self.pickerLayout, 27, 2, self.red, 1, 1 )

        self.button_Finger2_4_R  = self.button_create( self.pickerLayout, 24, 3, self.red, 1, 1 )
        self.button_Finger2_3_R  = self.button_create( self.pickerLayout, 25, 3, self.red, 1, 1 )
        self.button_Finger2_2_R  = self.button_create( self.pickerLayout, 26, 3, self.red, 1, 1 )
        self.button_Finger2_1_R  = self.button_create( self.pickerLayout, 27, 3, self.red, 1, 1 )

        self.button_Finger3_4_R  = self.button_create( self.pickerLayout, 24, 4, self.red, 1, 1 )
        self.button_Finger3_3_R  = self.button_create( self.pickerLayout, 25, 4, self.red, 1, 1 )
        self.button_Finger3_2_R  = self.button_create( self.pickerLayout, 26, 4, self.red, 1, 1 )
        self.button_Finger3_1_R  = self.button_create( self.pickerLayout, 27, 4, self.red, 1, 1 )

        self.button_Finger4_4_R  = self.button_create( self.pickerLayout, 24, 5, self.red, 1, 1 )
        self.button_Finger4_3_R  = self.button_create( self.pickerLayout, 25, 5, self.red, 1, 1 )
        self.button_Finger4_2_R  = self.button_create( self.pickerLayout, 26, 5, self.red, 1, 1 )
        self.button_Finger4_1_R  = self.button_create( self.pickerLayout, 27, 5, self.red, 1, 1 )

        self.button_Finger5_3_R  = self.button_create( self.pickerLayout, 25, 6, self.red, 1, 1 )
        self.button_Finger5_2_R  = self.button_create( self.pickerLayout, 26, 6, self.red, 1, 1 )
        self.button_Finger5_1_R  = self.button_create( self.pickerLayout, 27, 6, self.red, 1, 1 )

        self.button_Prop_R       = self.button_create( self.pickerLayout, 28, 4, self.red, 1, 1 )


        self.button_Finger5_3_L  = self.button_create( self.pickerLayout, 25, 8, self.blue, 1, 1 )
        self.button_Finger5_2_L  = self.button_create( self.pickerLayout, 26, 8, self.blue, 1, 1 )
        self.button_Finger5_1_L  = self.button_create( self.pickerLayout, 27, 8, self.blue, 1, 1 )

        self.button_Finger4_4_L  = self.button_create( self.pickerLayout, 24, 9, self.blue, 1, 1 )
        self.button_Finger4_3_L  = self.button_create( self.pickerLayout, 25, 9, self.blue, 1, 1 )
        self.button_Finger4_2_L  = self.button_create( self.pickerLayout, 26, 9, self.blue, 1, 1 )
        self.button_Finger4_1_L  = self.button_create( self.pickerLayout, 27, 9, self.blue, 1, 1 )

        self.button_Finger3_4_L  = self.button_create( self.pickerLayout, 24, 10, self.blue, 1, 1 )
        self.button_Finger3_3_L  = self.button_create( self.pickerLayout, 25, 10, self.blue, 1, 1 )
        self.button_Finger3_2_L  = self.button_create( self.pickerLayout, 26, 10, self.blue, 1, 1 )
        self.button_Finger3_1_L  = self.button_create( self.pickerLayout, 27, 10, self.blue, 1, 1 )

        self.button_Finger2_4_L  = self.button_create( self.pickerLayout, 24, 11, self.blue, 1, 1 )
        self.button_Finger2_3_L  = self.button_create( self.pickerLayout, 25, 11, self.blue, 1, 1 )
        self.button_Finger2_2_L  = self.button_create( self.pickerLayout, 26, 11, self.blue, 1, 1 )
        self.button_Finger2_1_L  = self.button_create( self.pickerLayout, 27, 11, self.blue, 1, 1 )

        self.button_Finger1_4_L  = self.button_create( self.pickerLayout, 24, 12, self.blue, 1, 1 )
        self.button_Finger1_3_L  = self.button_create( self.pickerLayout, 25, 12, self.blue, 1, 1 )
        self.button_Finger1_2_L  = self.button_create( self.pickerLayout, 26, 12, self.blue, 1, 1 )
        self.button_Finger1_1_L  = self.button_create( self.pickerLayout, 27, 12, self.blue, 1, 1 )

        self.button_Prop_L       = self.button_create( self.pickerLayout, 28, 10, self.blue, 1, 1 )

        ############################################################
        # Tool Tips

        self.button_Caput.setToolTip( 'All Head Controls')
        self.button_Leg_IK_L.setToolTip( 'All Left IK Leg Controls')
        self.button_Leg_IK_R.setToolTip( 'All Right IK Leg Controls')
        self.button_Leg_FK_L.setToolTip( 'All Left FK Leg Controls')
        self.button_Leg_FK_R.setToolTip( 'All Right FK Leg Controls')
        self.button_Arm_FK_R.setToolTip( 'All Right Arm FK Controls')
        self.button_Arm_FK_L.setToolTip( 'All Left Arm FK Controls')
        self.button_Arm_IK_R.setToolTip( 'All Right Arm IK Controls')
        self.button_Arm_IK_L.setToolTip( 'All Left Arm IK Controls')

        self.button_Spine.setToolTip( 'All Torso Controls')
        self.button_Eyes.setToolTip( 'Eyes')
        self.button_Eye_L.setToolTip( 'Eye Left')
        self.button_Eye_R.setToolTip( 'Eye Right')
        self.button_Jaw.setToolTip( 'Jaw')
        self.button_Head.setToolTip( 'Head')
        self.button_Neck.setToolTip( 'Neck')
        self.button_Spine3.setToolTip( 'Spine 3')
        self.button_Spine2.setToolTip( 'Spine 2')
        self.button_Spine1.setToolTip( 'Spine 1')
        self.button_Hips.setToolTip( 'Hips')

        self.button_Clavicle_L.setToolTip( 'Clavicle Left')
        self.button_ArmUp_L.setToolTip( 'Upper Arm Left')
        self.button_ArmLo_L.setToolTip( 'Lower Arm Left')
        self.button_Hand_L.setToolTip( 'Hand Left')
        self.button_ShoulderUpVec_L.setToolTip( 'Shoulder Up Vector Left')

        self.button_Clavicle_R.setToolTip( 'Clavicle Right')
        self.button_ArmUp_R.setToolTip( 'Upper Arm Right')
        self.button_ArmLo_R.setToolTip( 'Lower Arm Right')
        self.button_Hand_R.setToolTip( 'Hand Right')
        self.button_ShoulderUpVec_R.setToolTip( 'Shoulder Up Vector Right')

        self.button_Foot_IK_L.setToolTip( 'Foot Left')
        self.button_Ball_IK_L.setToolTip( 'Ball Left')
        self.button_Toes_IK_L.setToolTip( 'Toes Left')
        self.button_LegPole_IK_L.setToolTip( 'Pole Vector Left')
        self.button_Heel_IK_L.setToolTip( 'Heel Left')
        self.button_ToesTip_IK_L.setToolTip( 'Toes Tip Left')

        self.button_Foot_IK_R.setToolTip( 'Foot Right')
        self.button_Ball_IK_R.setToolTip( 'Ball Right')
        self.button_Toes_IK_R.setToolTip( 'Toes Right')
        self.button_LegPole_IK_R.setToolTip( 'Pole Vector Right')
        self.button_Heel_IK_R.setToolTip( 'Heel Right')
        self.button_ToesTip_IK_R.setToolTip( 'Toes Tip Right')

        self.button_Root.setToolTip( 'Root Motion')
        self.button_Main.setToolTip( 'Main')

        # Tool Tips
        ############################################################

        self.button_Finger1_1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['PinkyMeta_Rgt_Ctrl']}))
        self.button_Finger1_2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Rgt_Ctrl']}))
        self.button_Finger1_3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky2_Rgt_Ctrl']}))
        self.button_Finger1_4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky3_Rgt_Ctrl']}))

        self.button_Finger2_1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['RingMeta_Rgt_Ctrl']}))
        self.button_Finger2_2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring1_Rgt_Ctrl']}))
        self.button_Finger2_3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring2_Rgt_Ctrl']}))
        self.button_Finger2_4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring3_Rgt_Ctrl']}))

        self.button_Finger3_1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['MiddleMeta_Rgt_Ctrl']}))
        self.button_Finger3_2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle1_Rgt_Ctrl']}))
        self.button_Finger3_3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle2_Rgt_Ctrl']}))
        self.button_Finger3_4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle3_Rgt_Ctrl']}))

        self.button_Finger4_1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['IndexMeta_Rgt_Ctrl']}))
        self.button_Finger4_2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index1_Rgt_Ctrl']}))
        self.button_Finger4_3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index2_Rgt_Ctrl']}))
        self.button_Finger4_4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index3_Rgt_Ctrl']}))

        self.button_Finger5_1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb1_Rgt_Ctrl']}))
        self.button_Finger5_2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb2_Rgt_Ctrl']}))
        self.button_Finger5_3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb3_Rgt_Ctrl']}))

        self.button_Finger1_1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['PinkyMeta_Lft_Ctrl']}))
        self.button_Finger1_2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Lft_Ctrl']}))
        self.button_Finger1_3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky2_Lft_Ctrl']}))
        self.button_Finger1_4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky3_Lft_Ctrl']}))

        self.button_Finger2_1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['RingMeta_Lft_Ctrl']}))
        self.button_Finger2_2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring1_Lft_Ctrl']}))
        self.button_Finger2_3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring2_Lft_Ctrl']}))
        self.button_Finger2_4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring3_Lft_Ctrl']}))

        self.button_Finger3_1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['MiddleMeta_Lft_Ctrl']}))
        self.button_Finger3_2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle1_Lft_Ctrl']}))
        self.button_Finger3_3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle2_Lft_Ctrl']}))
        self.button_Finger3_4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle3_Lft_Ctrl']}))

        self.button_Finger4_1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['IndexMeta_Lft_Ctrl']}))
        self.button_Finger4_2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index1_Lft_Ctrl']}))
        self.button_Finger4_3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index2_Lft_Ctrl']}))
        self.button_Finger4_4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index3_Lft_Ctrl']}))

        self.button_Finger5_1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb1_Lft_Ctrl']}))
        self.button_Finger5_2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb2_Lft_Ctrl']}))
        self.button_Finger5_3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb3_Lft_Ctrl']}))

        self.button_Prop_L.clicked.connect( partial(self.picker_cmd, {'Nodes': ['Prop_Lft_Ctrl']}))
        self.button_Prop_R.clicked.connect( partial(self.picker_cmd, {'Nodes': ['Prop_Rgt_Ctrl']}))


        self.button2_Finger1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Rgt_Ctrl',
                                                                                   'Pinky3_Rgt_Ctrl',
                                                                                   'Pinky2_Rgt_Ctrl']}))

        self.button2_Finger2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring1_Rgt_Ctrl',
                                                                                   'Ring3_Rgt_Ctrl',
                                                                                   'Ring2_Rgt_Ctrl']}))

        self.button2_Finger3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle1_Rgt_Ctrl',
                                                                                   'Middle3_Rgt_Ctrl',
                                                                                   'Middle2_Rgt_Ctrl']}))

        self.button2_Finger4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index1_Rgt_Ctrl',
                                                                                   'Index3_Rgt_Ctrl',
                                                                                   'Index2_Rgt_Ctrl' ]}))

        self.button2_Finger5_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb1_Rgt_Ctrl',
                                                                                   'Thumb2_Rgt_Ctrl',
                                                                                   'Thumb3_Rgt_Ctrl' ]}))

        self.button2_Finger1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Lft_Ctrl',
                                                                                   'Pinky3_Lft_Ctrl',
                                                                                   'Pinky2_Lft_Ctrl']}))

        self.button2_Finger2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Ring1_Lft_Ctrl',
                                                                                   'Ring3_Lft_Ctrl',
                                                                                   'Ring2_Lft_Ctrl']}))

        self.button2_Finger3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Middle2_Lft_Ctrl',
                                                                                   'Middle3_Lft_Ctrl',
                                                                                   'Middle1_Lft_Ctrl']}))

        self.button2_Finger4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Index2_Lft_Ctrl',
                                                                                   'Index3_Lft_Ctrl',
                                                                                   'Index1_Lft_Ctrl']}))

        self.button2_Finger5_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Thumb1_Lft_Ctrl',
                                                                                   'Thumb2_Lft_Ctrl',
                                                                                   'Thumb3_Lft_Ctrl']}))

        self.button2_Digits1_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['PinkyMeta_Rgt_Ctrl',
                                                                                   'IndexMeta_Rgt_Ctrl',
                                                                                   'RingMeta_Rgt_Ctrl',
                                                                                   'MiddleMeta_Rgt_Ctrl']}))

        self.button2_Digits2_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Rgt_Ctrl',
                                                                                   'Ring1_Rgt_Ctrl',
                                                                                   'Middle1_Rgt_Ctrl',
                                                                                   'Index1_Rgt_Ctrl']}))

        self.button2_Digits3_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky2_Rgt_Ctrl',
                                                                                   'Ring2_Rgt_Ctrl',
                                                                                   'Middle2_Rgt_Ctrl',
                                                                                   'Index2_Rgt_Ctrl']}))

        self.button2_Digits4_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky3_Rgt_Ctrl',
                                                                                   'Ring3_Rgt_Ctrl',
                                                                                   'Middle3_Rgt_Ctrl',
                                                                                   'Index3_Rgt_Ctrl']}))

        self.button2_Digits1_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky1_Lft_Ctrl',
                                                                                   'Ring1_Lft_Ctrl',
                                                                                   'Middle1_Lft_Ctrl',
                                                                                   'Index1_Lft_Ctrl']}))

        self.button2_Digits2_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky2_Lft_Ctrl',
                                                                                   'Ring2_Lft_Ctrl',
                                                                                   'Middle2_Lft_Ctrl',
                                                                                   'Index2_Lft_Ctrl']}))

        self.button2_Digits3_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky3_Lft_Ctrl',
                                                                                   'Ring3_Lft_Ctrl',
                                                                                   'Middle3_Lft_Ctrl',
                                                                                   'Index3_Lft_Ctrl']}))

        self.button2_Digits4_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['Pinky4_Lft_Ctrl',
                                                                                   'Ring4_Lft_Ctrl',
                                                                                   'Middle4_Lft_Ctrl',
                                                                                   'Index4_Lft_Ctrl']}))

        self.button_Hand_L.clicked.connect(partial(self.picker_cmd, {'Nodes': ['PinkyMeta_Lft_Ctrl',
                                                                                   'RingMeta_Lft_Ctrl',
                                                                                   'MiddleMeta_Lft_Ctrl',
                                                                                   'IndexMeta_Lft_Ctrl',
                                                                                   'Pinky3_Lft_Ctrl',
                                                                                   'Ring3_Lft_Ctrl',
                                                                                   'Middle3_Lft_Ctrl',
                                                                                   'Index3_Lft_Ctrl',
                                                                                   'Pinky2_Lft_Ctrl',
                                                                                   'Ring2_Lft_Ctrl',
                                                                                   'Middle2_Lft_Ctrl',
                                                                                   'Index2_Lft_Ctrl',
                                                                                   'Pinky1_Lft_Ctrl',
                                                                                   'Ring1_Lft_Ctrl',
                                                                                   'Middle1_Lft_Ctrl',
                                                                                   'Index1_Lft_Ctrl',
                                                                                   'Thumb1_Lft_Ctrl',
                                                                                   'Thumb2_Lft_Ctrl',
                                                                                   'Thumb3_Lft_Ctrl' ]}))

        self.button_Hand_R.clicked.connect(partial(self.picker_cmd, {'Nodes': ['PinkyMeta_Rgt_Ctrl',
                                                                                   'RingMeta_Rgt_Ctrl',
                                                                                   'MiddleMeta_Rgt_Ctrl',
                                                                                   'IndexMeta_Rgt_Ctrl',
                                                                                   'Pinky3_Rgt_Ctrl',
                                                                                   'Ring3_Rgt_Ctrl',
                                                                                   'Middle3_Rgt_Ctrl',
                                                                                   'Index3_Rgt_Ctrl',
                                                                                   'Pinky2_Rgt_Ctrl',
                                                                                   'Ring2_Rgt_Ctrl',
                                                                                   'Middle2_Rgt_Ctrl',
                                                                                   'Index2_Rgt_Ctrl',
                                                                                   'Pinky1_Rgt_Ctrl',
                                                                                   'Ring1_Rgt_Ctrl',
                                                                                   'Middle1_Rgt_Ctrl',
                                                                                   'Index1_Rgt_Ctrl',
                                                                                   'Thumb1_Rgt_Ctrl',
                                                                                   'Thumb2_Rgt_Ctrl',
                                                                                   'Thumb3_Rgt_Ctrl' ]}))
        #mainLayout.addLayout( self.pickerLayout )
        mainLayout.addWidget(  self.pickerWidget )
        self.pickerLayout.update()

    def picker_cmd(self, *args  ):

        data = args[0]

        char =  self.charList.currentText()

        if char == '':
            self.char_list_refresh()
            char =  self.charList.currentText()

        if mc.objExists(char):

            mode = 'Select'
            nodes = []
            switch = False

            if 'Nodes' in data:
                nodes = data['Nodes']
            if 'Mode' in data:
                mode = data['Mode']
            if 'Switch' in data:
                switch = data['Switch']

            if mode == 'Select':
                nodes_long = []

                for node in nodes:
                    try:
                        nodes_long.append( self.am.find_node( char, node) )
                    except:
                        mc.warning('aniMeta Picker: Can not find node', node)

                mods = mc.getModifiers()

                keyModifier = None

                if (mods & 1) > 0:
                    keyModifier = 'Shift'
                if (mods & 4) > 0:
                    keyModifier = 'Ctrl'

                if len ( nodes_long ) > 0:
                    if mode == 'Select' and keyModifier is None:
                        mc.select( nodes_long, r=True )
                    if mode == 'Select' and keyModifier == 'Shift':
                        mc.select( nodes_long, tgl=True )
                    if mode == 'Select' and keyModifier == 'Ctrl':
                        mc.select( nodes_long, deselect=True)
            # Arm IK
            if mode == 'Arm_IK_R':
                if switch:
                    data = {'Character': char, 'Limb': 'Arm', 'Side': 'Rgt'}
                    self.arm_mode_R = Biped().switch_fkik(**data)
                else:
                    self.arm_mode_R = 1 - self.arm_mode_R

            if mode == 'Arm_FK_R':
                if switch:
                    data = {'Character': char, 'Limb': 'Arm', 'Side': 'Rgt'}
                    self.arm_mode_R = Biped().switch_fkik(**data)
                else:
                    self.arm_mode_R = kFK

            if mode == 'Arm_IK_L':
                if switch:
                    data = {'Character': char, 'Limb': 'Arm', 'Side': 'Lft'}
                    self.arm_mode_L = Biped().switch_fkik(**data)
                else:
                    self.arm_mode_L = 1 - self.arm_mode_L

            if mode == 'Arm_FK_L':
                self.arm_mode_L = kFK

            # Leg IK
            if mode == 'Leg_IK_R':
                if switch:
                    data = {'Character': char, 'Limb': 'Leg', 'Side': 'Rgt'}
                    self.leg_mode_R = Biped().switch_fkik(**data)
                else:
                    self.leg_mode_R = 1 - self.leg_mode_R

            if mode == 'Leg_FK_R':
                self.leg_mode_R = kFK

            if mode == 'Leg_IK_L':
                if switch:
                    data = {'Character': char, 'Limb': 'Leg', 'Side': 'Lft'}
                    self.leg_mode_L = Biped().switch_fkik(**data)
                else:
                    self.leg_mode_L = 1 - self.leg_mode_L

            if mode == 'Leg_FK_L':
                self.leg_mode_L = kFK

            self.ui_update()

    def set_global_scale(self, *args ):
        char = self.am.get_active_char()
        if char is not None:
            try:
                mc.setAttr( char + '.globalScale', self.globalScale.value() )
            except:
                pass

    def set_ctrl_scale(self, *args ):
        char = self.am.get_active_char()
        if char is not None:
            try:
                mc.setAttr( char + '.globalCtrlScale', self.ctrlScale.value() )
            except:
                pass

    def set_joint_radius(self, *args ):
        char = self.am.get_active_char()
        if char is not None:
            try:
                mc.setAttr( char + '.jointRadius', self.jointRadius.value() )
            except:
                pass

    def set_joint_display(self):
        mode = self.jointMode.currentIndex()
        if self.char is not None:
            try:
                mc.setAttr ( self.char + '.display_Joint', mode )
            except:
                pass

    def set_geo_display(self):
        mode = self.geoMode.currentIndex()
        if self.char is not None:
            try:
                mc.setAttr ( self.char + '.display_Geo', mode )
            except:
                pass

    def get_widget_state(self, widget):

        state = widget.checkState()
        if state == QtCore.Qt.CheckState.Unchecked:
            return 0
        else:
            return 1

    def show_character(self, *args):
        char = self.am.get_active_char( )
        if char is not None:
            try:
                state = self.get_widget_state(self.showChar)
                mc.setAttr( char + '.v', state/2 )
            except:
                pass
        else:
            self.ui_update()

    def show_rig(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showRig)
                mc.setAttr( char + '.show_Rig', state/2 )
            except:
                pass

    def show_geo(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showGeo)
                mc.setAttr( char + '.show_Geo', state/2 )
            except:
                pass

    def show_joints(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showJoints)
                mc.setAttr( char + '.show_Joints', state/2 )
            except:
                pass

    def show_guides(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showGuides)
                mc.setAttr( char + '.show_Guides', state/2 )
            except:
                pass

    def show_mocap(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showMocap)
                mc.setAttr( char + '.show_Mocap', state/2 )
            except:
                pass

    def show_upVecs(self, *args):
        char = self.am.get_active_char()
        if char is not None:
            try:
                state = self.get_widget_state(self.showUpVecs)
                mc.setAttr( char + '.show_UpVectors', state/2 )
            except:
                pass

    def update_value_widget( self, char, widget, attribute ):

        try:
            gs = mc.getAttr( char + '.' + attribute )
            widget.setValue( gs )
        except:
            #mc.warning('aniMeta: Can not find globalScale attribute.')
            pass

    def update_state_widget( self, char, widget, attribute ):

        try:
            sj = mc.getAttr( char + '.' + attribute )
            widget.setCheckState(self.get_state(sj))
        except:
            #mc.warning('aniMeta: Can not find globalScale attribute.')
            pass

    def update_enum_widget( self, char, widget, attribute ):

        try:
            sj = mc.getAttr( char + '.' + attribute )
            widget.setCurrentIndex(sj)
        except:
            #mc.warning('aniMeta: Can not find globalScale attribute.')
            pass

    def ui_update( self, char=None ):

        if char is None:
            char = self.am.get_active_char()

        if char is not None:

            if mc.objExists( char ):

                self.ui_enable( True )

                v   = mc.getAttr(char + '.v')

                data = self.am.get_metaData(char)

                ######################################################################
                # Update the Display Options Widgets

                if 'RigState' in data:
                    state = data['RigState']
                    self.pickerWidget.setEnabled( state-1 )

                self.update_value_widget( char, self.globalScale,  'globalScale'     )
                self.update_value_widget( char, self.ctrlScale,    'globalCtrlScale' )
                self.update_value_widget( char, self.jointRadius,  'jointRadius'     )

                self.update_state_widget( char, self.showJoints,   'show_Joints'     )
                self.update_state_widget( char, self.showGuides,   'show_Guides'     )
                self.update_state_widget( char, self.showRig,      'show_Rig'        )
                self.update_state_widget( char, self.showGeo,      'show_Geo'        )
                self.update_state_widget( char, self.showMocap,    'show_Mocap'      )
                self.update_state_widget( char, self.showUpVecs,   'show_UpVectors'  )

                self.update_enum_widget(  char, self.jointMode,   'display_Joint'    )
                self.update_enum_widget(  char, self.geoMode,     'display_Geo'      )

                self.showChar.setCheckState( self.get_state(v) )

                # Save the current char
                self.char = char

                metaData = self.am.get_metaData(char)


                if 'RigState' in metaData:
                    rigState = metaData['RigState']

                    if rigState == kRigStateControl:
                        self.modeControls.setEnabled(False)
                        self.modeControls.setStyleSheet(self.style_active)
                        self.modeControls.setToolTip( 'Rig is in control mode.')

                        self.modeGuides.setEnabled(True)
                        self.modeGuides.setStyleSheet(self.style_not_active)
                        self.modeGuides.setToolTip( 'Switch the rig to guide mode.')
                        self.lockGuides1.setEnabled(False)
                        self.lockGuides2.setEnabled(False)
                        self.lockGuides3.setEnabled(False)
                    else:
                        self.modeControls.setEnabled(True)
                        self.modeControls.setStyleSheet(self.style_not_active)
                        self.modeControls.setToolTip( 'Switch the rig to control mode.')

                        self.modeGuides.setEnabled(False)
                        self.modeGuides.setStyleSheet(self.style_active)
                        self.modeGuides.setToolTip( 'Rig is in guide mode.')
                        self.lockGuides1.setEnabled(True)
                        self.lockGuides2.setEnabled(True)
                        self.lockGuides3.setEnabled(True)

                # Arm IK R
                if self.arm_mode_R == kFK:
                    self.button_ik_arm_R.setEnabled( True )
                    self.button_ik_arm_R.setStyleSheet(self.style_not_active)
                    self.button_fk_arm_R.setEnabled( False )
                    self.button_fk_arm_R.setStyleSheet(self.style_active)

                    for widget in self.buttons_arm_ik_R:
                        widget.setVisible( False )
                    for widget in self.buttons_arm_fk_R:
                        widget.setVisible( True )
                else:
                    self.button_ik_arm_R.setEnabled( False )
                    self.button_ik_arm_R.setStyleSheet(self.style_active)
                    self.button_fk_arm_R.setEnabled( True )
                    self.button_fk_arm_R.setStyleSheet(self.style_not_active)

                    for widget in self.buttons_arm_ik_R:
                        widget.setVisible( True )
                    for widget in self.buttons_arm_fk_R:
                        widget.setVisible( False )

                # Arm IK L
                if self.arm_mode_L == kFK:
                    self.button_ik_arm_L.setEnabled( True )
                    self.button_ik_arm_L.setStyleSheet(self.style_not_active)
                    self.button_fk_arm_L.setEnabled( False )
                    self.button_fk_arm_L.setStyleSheet(self.style_active)

                    for widget in self.buttons_arm_ik_L:
                        widget.setVisible( False )
                    for widget in self.buttons_arm_fk_L:
                        widget.setVisible( True )
                else:
                    self.button_ik_arm_L.setEnabled( False )
                    self.button_ik_arm_L.setStyleSheet(self.style_active)
                    self.button_fk_arm_L.setEnabled( True )
                    self.button_fk_arm_L.setStyleSheet(self.style_not_active)

                    for widget in self.buttons_arm_ik_L:
                        widget.setVisible( True )
                    for widget in self.buttons_arm_fk_L:
                        widget.setVisible( False )

                # Leg IK R
                if self.leg_mode_R == kFK:
                    self.button_ik_leg_R.setEnabled( True )
                    self.button_ik_leg_R.setStyleSheet(self.style_not_active)
                    self.button_fk_leg_R.setEnabled( False )
                    self.button_fk_leg_R.setStyleSheet(self.style_active)

                    for widget in self.buttons_leg_ik_R:
                        widget.setVisible( False )
                    for widget in self.buttons_leg_fk_R:
                        widget.setVisible( True )
                else:
                    self.button_ik_leg_R.setEnabled( False )
                    self.button_ik_leg_R.setStyleSheet(self.style_active)
                    self.button_fk_leg_R.setEnabled( True )
                    self.button_fk_leg_R.setStyleSheet(self.style_not_active)

                    for widget in self.buttons_leg_ik_R:
                        widget.setVisible( True )
                    for widget in self.buttons_leg_fk_R:
                        widget.setVisible( False )

                # Leg IK L
                if self.leg_mode_L == kFK:
                    self.button_ik_leg_L.setEnabled( True )
                    self.button_ik_leg_L.setStyleSheet(self.style_not_active)
                    self.button_fk_leg_L.setEnabled( False )
                    self.button_fk_leg_L.setStyleSheet(self.style_active)

                    for widget in self.buttons_leg_ik_L:
                        widget.setVisible( False )
                    for widget in self.buttons_leg_fk_L:
                        widget.setVisible( True )
                else:
                    self.button_ik_leg_L.setEnabled( False )
                    self.button_ik_leg_L.setStyleSheet(self.style_active)
                    self.button_fk_leg_L.setEnabled( True )
                    self.button_fk_leg_L.setStyleSheet(self.style_not_active)

                    for widget in self.buttons_leg_ik_L:
                        widget.setVisible( True )
                    for widget in self.buttons_leg_fk_L:
                        widget.setVisible( False )

                self.pickerLayout.update()
            else:
                self.ui_enable( False )
        else:
            self.ui_enable( False )

    def ui_enable(self, mode):
            self.showChar.setEnabled(mode)
            self.showJoints.setEnabled(mode)
            self.showGeo.setEnabled(mode)
            self.showRig.setEnabled(mode)
            self.showGuides.setEnabled(mode)
            self.showMocap.setEnabled(mode)
            self.showUpVecs.setEnabled(mode)
            self.globalScale.setEnabled(mode)
            self.ctrlScale.setEnabled(mode)
            self.jointRadius.setEnabled(mode)
            self.jointMode.setEnabled(mode)
            self.geoMode.setEnabled(mode)
            self.modeControls.setEnabled(mode)
            self.modeGuides.setEnabled(mode)
            self.lockGuides1.setEnabled(mode)
            self.lockGuides2.setEnabled(mode)
            self.lockGuides3.setEnabled(mode)
            self.pickerWidget.setEnabled(mode)

            if not mode:
                self.modeControls.setStyleSheet(self.style_not_active)
                self.modeGuides.setStyleSheet(self.style_not_active)


class LibTab(QWidget):

    charList = None
    resized = Signal()

    pose_path = None

    pose = None

    def __init__(self, *argv, **keywords):
        super(LibTab, self).__init__( )

        self.am = AniMeta()
        self.rig = Rig()
        mainLayout = QVBoxLayout( self )

        self.setLayout(mainLayout)

        self.menu = QMenu( self )

        l_widget = QWidget()
        self.l = QVBoxLayout( l_widget )
        self.l.setSpacing(px(2))
        self.l.setContentsMargins( px(8), px(4), px(8), px(4) )

        self.scrollArea = QScrollArea()
        self.layout().addWidget( self.scrollArea )

        self.scrollArea.setWidget( l_widget )
        self.scrollArea.setWidgetResizable(True)

        self.kPose, self.kAnim = range(2)

        self.pose_column_count = 3
        self.anim_column_count = 3
        self.rig_column_count = 3

        self.pose_root = self.am.folder_pose
        self.pose_path = self.am.folder_pose

        self.anim_root = self.am.folder_anim
        self.anim_path = self.am.folder_anim

        self.rig_root = self.am.folder_rig
        self.rig_path = self.am.folder_rig

        self.pose_grid = QGridLayout()
        self.anim_grid = QGridLayout()
        self.rig_grid  = QGridLayout()

        self.button_height = 28
        self.button_width = 128

        # Poses Frame Widget
        self.poses()

        # Animation Frame Widget
        self.anims()

        # Rig Frame Widget
        self.rigs()

        for section in [kLibPose, kLibAnim, kLibRig ]:
            self.tree_refresh( section )
            self.refresh( section )

        self.l.addStretch()

    def resizeEvent( self, event ):

        self.check_columns( kLibPose )
        self.check_columns( kLibAnim )
        self.check_columns( kLibRig )


    def poses( self ):

        ########################################
        #   Poses

        self.pose_frame = FrameWidget( 'Poses', None )
        self.l.addWidget( self.pose_frame )

        widget = QWidget( self.pose_frame )

        vLayout = QVBoxLayout( self )

        self.pose_frame.setLayout( vLayout )

        hLayout = QHBoxLayout( self )

        vLayout.addLayout( hLayout )

        # Buttons
        button1 = QPushButton( 'Save' )
        button2 = QPushButton( 'Load' )

        button1.clicked.connect( self.pose_export_dialog )

        for button in [ button1, button2 ]:
            button.setMinimumWidth( self.button_width )
            button.setMaximumWidth( self.button_width )
            button.setMinimumHeight( self.button_height )
            button.setMaximumHeight( self.button_height )

        hLayout.addWidget( button1 )
        hLayout.addWidget( button2 )
        hLayout.addStretch()

        # Split Layout
        self.pose_split = QSplitter( Qt.Horizontal )
        self.pose_split.splitterMoved.connect( partial( self.check_columns, kLibPose ) )

        # Tree View

        self.pose_tree_scroll = QScrollArea()
        #self.pose_tree_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOn )
        self.pose_tree_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.pose_tree_scroll.setWidgetResizable( True )

        self.pose_tree_view = aniMetaTreeWidget()
        self.pose_tree_view.setHeaderLabel( 'Pose Folders' )

        self.pose_tree_view.installEventFilter( self )
        self.pose_tree_view.setContextMenuPolicy( QtCore.Qt.CustomContextMenu )
        self.pose_tree_view.customContextMenuRequested.connect(  self.pose_tree_ctx_menu )

        self.pose_tree_scroll.setWidget( self.pose_tree_view )

        self.pose_tree_view.selectionModel().selectionChanged.connect( partial ( self.tree_select, kLibPose ) )

        self.pose_split.addWidget( self.pose_tree_scroll )

        # Pose Panel
        self.pose_scroll = QScrollArea()
        self.pose_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOn )
        self.pose_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.pose_scroll.setWidgetResizable( True )
        self.pose_split.addWidget( self.pose_scroll )

        vLayout.addWidget( self.pose_split )

        self.pose_frame.setCollapsed( True )

    #   Poses
    ########################################


    ########################################
    #   Animation

    def anims( self ):

        self.anim_frame = FrameWidget( 'Animation', None )
        self.l.addWidget( self.anim_frame )

        widget = QWidget( self.anim_frame )

        vLayout = QVBoxLayout( self )
        self.anim_frame.setLayout( vLayout )

        hLayout = QHBoxLayout( self )

        vLayout.addLayout( hLayout )

        # Buttons
        button1 = QPushButton( 'Save' )
        button2 = QPushButton( 'Load' )

        button1.clicked.connect( self.export_anim_dialog )

        for button in [ button1, button2 ]:
            button.setMinimumWidth( self.button_width )
            button.setMaximumWidth( self.button_width )
            button.setMinimumHeight( self.button_height )
            button.setMaximumHeight( self.button_height )

        hLayout.addWidget( button1 )
        hLayout.addWidget( button2 )
        hLayout.addStretch()

        # Split Layout
        self.anim_split = QSplitter( Qt.Horizontal )
        self.anim_split.splitterMoved.connect( partial ( self.check_columns, kLibAnim ) )

        # Tree View

        self.anim_tree_scroll = QScrollArea()
        #self.anim_tree_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOn )
        self.anim_tree_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.anim_tree_scroll.setWidgetResizable( True )

        self.anim_tree_view = aniMetaTreeWidget()
        self.anim_tree_view.setHeaderLabel( 'Animation Folders' )

        self.anim_tree_view.installEventFilter( self )
        self.anim_tree_view.setContextMenuPolicy( QtCore.Qt.CustomContextMenu )
        self.anim_tree_view.customContextMenuRequested.connect( self.anim_tree_ctx_menu   )

        self.anim_tree_scroll.setWidget( self.anim_tree_view )

        self.anim_tree_view.selectionModel().selectionChanged.connect( partial ( self.tree_select, kLibAnim ) )

        self.anim_split.addWidget( self.anim_tree_scroll )


        # Animation Panel
        self.anim_scroll = QScrollArea()
        self.anim_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOn )
        self.anim_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.anim_scroll.setWidgetResizable( True )
        self.anim_split.addWidget( self.anim_scroll )

        vLayout.addWidget( self.anim_split )

        self.anim_frame.setCollapsed( True )

    #   Animation
    ########################################


    ########################################
    #   Rig Settings

    def rigs( self ):

        self.rig_frame = FrameWidget( 'Rigs', None  )
        self.l.addWidget( self.rig_frame )

        widget = QWidget( self.rig_frame )

        vLayout = QVBoxLayout( self )
        self.rig_frame.setLayout( vLayout )

        hLayout = QHBoxLayout( self )

        vLayout.addLayout( hLayout )

        # Buttons
        button1 = QPushButton( 'Save' )
        button2 = QPushButton( 'Load' )

        button1.clicked.connect( self.rig_export_dialog )

        for button in [ button1, button2 ]:
            button.setMinimumWidth( self.button_width )
            button.setMaximumWidth( self.button_width )
            button.setMinimumHeight( self.button_height )
            button.setMaximumHeight( self.button_height )

        hLayout.addWidget( button1 )
        hLayout.addWidget( button2 )
        hLayout.addStretch()

        # Split Layout
        self.rig_split = QSplitter( Qt.Horizontal )
        self.rig_split.splitterMoved.connect( partial ( self.check_columns, kLibRig ) )

        # Tree View

        self.rig_tree_scroll = QScrollArea()
        self.rig_tree_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAsNeeded )
        self.rig_tree_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.rig_tree_scroll.setWidgetResizable( True )

        self.rig_tree_view = aniMetaTreeWidget()
        self.rig_tree_view.setHeaderLabel( 'Rig Settings Folders' )

        self.rig_tree_view.installEventFilter( self )
        self.rig_tree_view.setContextMenuPolicy( QtCore.Qt.CustomContextMenu )
        self.rig_tree_view.customContextMenuRequested.connect( self.rig_tree_ctx_menu   )

        self.rig_tree_scroll.setWidget( self.rig_tree_view )

        self.rig_tree_view.selectionModel().selectionChanged.connect( partial ( self.tree_select, kLibRig ) )

        self.rig_split.addWidget( self.rig_tree_scroll )

        # Animation Panel
        self.rig_scroll = QScrollArea()
        self.rig_scroll.setVerticalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOn )
        self.rig_scroll.setHorizontalScrollBarPolicy( QtCore.Qt.ScrollBarAlwaysOff )
        self.rig_scroll.setWidgetResizable( True )
        self.rig_split.addWidget( self.rig_scroll )

        vLayout.addWidget( self.rig_split )

        self.rig_frame.setCollapsed( True )

    #   Rig Settings
    ########################################

    def check_columns( self, *args ):

        section = args[0]

        if section == kLibPose:
            sizes = self.pose_split.sizes()
            column_count = self.pose_column_count
        elif section == kLibAnim:
            sizes = self.anim_split.sizes()
            column_count = self.anim_column_count
        elif section == kLibRig:
            sizes = self.rig_split.sizes()
            column_count = self.rig_column_count


        # new_count = abs ( (self.width() - 130 ) / 256 )
        new_count = abs( (sizes[ 1 ] - 48) / 256 )

        if new_count < 1:
            new_count = 1

        if new_count != column_count:

            if section == kLibPose:
                self.pose_column_count = new_count
            elif section == kLibAnim:
                self.anim_column_count = new_count
            elif section == kLibRig:
                self.rig_column_count = new_count

            self.refresh( section )

    def tree_refresh( self, section=kLibPose ):

        folders = { }

        count = 0

        abs_path = os.path.abspath( self.get_root(section) )
        abs_path = abs_path.replace( '\\', '/' )

        if section == kLibPose:
            tree_view = self.pose_tree_view
        elif section == kLibAnim:
            tree_view = self.anim_tree_view
        elif section == kLibRig:
            tree_view = self.rig_tree_view

        for i in range( tree_view.topLevelItemCount() ):
            tree_view.takeTopLevelItem( i )

        root_item = QTreeWidgetItem( [ abs_path ] )
        tree_view.addTopLevelItem( root_item )
        root_item.setExpanded( True )

        for root, subdirs, files in os.walk( abs_path ):

            abs_root = os.path.abspath( root )
            abs_root = abs_root.replace( '\\', '/' )

            for subdir in subdirs:

                # Create an item
                item = QTreeWidgetItem( [ subdir ] )
                item.setChildIndicatorPolicy( QTreeWidgetItem.DontShowIndicator )

                folders[ abs_root + '/' + subdir ] = item

                if abs_root in folders:
                    parent = folders[ abs_root ]

                    parent.addChild( item )

                    index = tree_view.get_index( parent )
                    tree_view.setExpanded( index, True )

                    parent.setChildIndicatorPolicy( QTreeWidgetItem.DontShowIndicatorWhenChildless )
                else:
                    root_item.addChild( item )
            count += 1

    def tree_select( self, *args, **kwargs ):

        section = args[0]
        item    = QItemSelection(args[1])
        indices = item.indexes()

        if section == kLibPose:
            tree_view = self.pose_tree_view
        if section == kLibAnim:
            tree_view = self.anim_tree_view
        if section == kLibRig:
            tree_view = self.rig_tree_view

        if indices:
            item = QTreeWidgetItem(  tree_view.itemFromIndex( indices[0] ) )
            item = item.parent()

            current = item
            parents = []

            count = 0
            max = 100

            while current.parent() is not None:

                parent = current.parent()

                if parent is not None:
                    current = parent
                    parents.append( parent.text(0))

                # Safety measure for loop
                count += 1
                if count == max:
                    break

            # We need to reverse it to get a proper folder order
            parents.reverse()
            parents.append(item.text(0))

            root = self.get_root( section )

            path = root

            for parent in parents:
                path = os.path.join( path , parent )

            # Make the path have consistent slashes
            path = os.path.abspath( path )


            if section == kLibPose:
                self.pose_path = path
                mc.optionVar( sv=['aniMeta_lib_pose_path', path])
            elif section == kLibAnim:
                self.anim_path = path
            elif section == kLibRig:
                self.rig_path = path

            self.refresh( section )
 
    def delete( self ):
        self.pose_container.deleteLater()

    def get_path( self, section ):
        if section == kLibPose:
            return self.pose_path
        elif section == kLibAnim:
            return self.anim_path
        elif section == kLibRig:
            return self.rig_path

    def get_root( self, section ):
        if section == kLibPose:
            return self.pose_root
        elif section == kLibAnim:
            return self.anim_root
        elif section == kLibRig:
            return self.rig_root

    def refresh( self, section=kLibPose ):

        content = None

        chars = self.am.get_metaData( None, {'Type': kBiped  })

        if chars is not None:
            for char in chars:
                QListWidgetItem( char, self.list)

        path = self.get_path(section)

        #if section == kLibPose:
        #    mc.optionVar(sv=['aniMeta_lib_pose_path', path])

        try:
            content = os.listdir( path )
        except OSError as err:
            print("OS error: {0}".format(err))

        json_files = []

        if content:
            for c in content:
                if '.json' in c:
                    json_files.append( c )

        json_files.sort()

        row = 0
        buttons = []
        column = 0

        if section == kLibPose:
            grid = self.pose_grid
            self.pose_container = QWidget()
            container = self.pose_container
            column_count = self.pose_column_count
        elif section == kLibAnim:
            grid = self.anim_grid
            self.anim_container = QWidget()
            container = self.anim_container
            column_count = self.anim_column_count
        elif section == kLibRig:
            grid = self.rig_grid
            self.rig_container = QWidget()
            container = self.rig_container
            column_count = self.rig_column_count
        try:
            grid.deleteLater()
        except:
            pass

        grid = QGridLayout()
        container.setLayout( grid )

        if section == kLibPose:
            self.pose_scroll.setWidget( container )
        if section == kLibAnim:
            self.anim_scroll.setWidget( container )
        if section == kLibRig:
            self.rig_scroll.setWidget( container )

        if section == kLibPose:
            ctx_menu = self.pose_item_ctx_menu
        if section == kLibAnim:
            ctx_menu = self.anim_item_ctx_menu
        if section == kLibRig:
            ctx_menu = self.rig_item_ctx_menu


        for i in range( len(json_files) ):

            if column == column_count:
                column = 0
                row += 1
            #button = QPushButton( json_files[i].split('.')[0] )
            button = aniMetaLibItem(json_files[i].split('.')[0])

            button.installEventFilter( self )
            button.setContextMenuPolicy( QtCore.Qt.CustomContextMenu )
            button.customContextMenuRequested.connect( ctx_menu )


            button.setMenu( self.menu )

            button.setFixedSize( 256, 256 )

            png_file_name = json_files[i].replace('json', 'png')

            png_file_path = self.get_path( section ).replace('\\', '/') +'/' + png_file_name

            if os.path.isfile( png_file_path ):

                button.setStyleSheet( "QPushButton{background-image: url('"+png_file_path+"'); "
                                      "background-repeat: no-repeat;"
                                      "border: 4px solid grey;"
                                      "text-align:bottom;"
                                      "padding-bottom:6px;"
                                      "border-radius: 8px}" 
                                      "QPushButton:hover {border: 4px solid white;}")

            grid.addWidget( button, row, column )
            buttons.append( button )

            column +=1

    def pose_export_dialog( self, *args, **kwargs ):

        char = self.am.get_active_char()

        if char is not None :

            self.pose_ui = 'aniMetaSavePoseUI'

            if mc.window( self.pose_ui, exists=True ):
                mc.deleteUI( self.pose_ui )

            mc.window( self.pose_ui, title='Save Pose', w=200, h=100, rtf=True )

            mc.rowColumnLayout( numberOfColumns = 1, rs=[1,10], ro=[1,'top',10] )

            self.pose_export_name_ctrl = mc.textFieldGrp(  label='Pose Name' )

            if mc.optionVar( exists='aniMetaExportPoseHandleMode' ):
                select = mc.optionVar(  query='aniMetaExportPoseHandleMode')
            else:
                select = 1

            self.pose_export_sel_ctrl = mc.radioButtonGrp(label='Handles', labelArray2=['All', 'Selected'], numberOfRadioButtons=2, select=select)

            row2 = mc.rowColumnLayout( numberOfColumns = 2, cs=[1,10] )
            mc.rowColumnLayout( row2, e=True,  cs = [ 2, 10 ] )

            mc.button( label = 'Save', width = 120, command = self.pose_export_doit )
            mc.button( label = 'Cancel', width = 120, command = partial( self.close_export_dialog, self.pose_ui )  )

            mc.showWindow()

        else:
            mc.warning( 'No Handles to export animation from.' )

    def pose_export_doit( self, *args, **kwargs ):

        pose_name = mc.textFieldGrp( self.pose_export_name_ctrl, q=True, text=True )
        handle_mode = mc.radioButtonGrp( self.pose_export_sel_ctrl , query=True, select=True )

        mc.optionVar( intValue=('aniMetaExportPoseHandleMode', handle_mode) )

        if mc.window( self.pose_ui, exists = True ):
            mc.deleteUI( self.pose_ui )

        char = self.am.get_active_char()

        if char is not None:

            poseDict = self.rig.get_pose( matrix_as_list=True, handle_mode=handle_mode )

            pretty_json = json.dumps( poseDict, indent=4, sort_keys=True)

            full_file_path = os.path.join( os.path.abspath(self.pose_path), pose_name + '.json' )

            if os.path.isdir( full_file_path ):

                result = mc.confirmDialog(
                    title='Folder exists',
                    message='A folder by this name exists\nAborting operation',
                    button=['OK' ],
                    defaultButton='OK' )

                return False

            if os.path.isfile( full_file_path ):

                result = mc.confirmDialog(
                    title='Overwrite File',
                    message='A file by this name exists\nOverwrite existing file?',
                    button=['Yes', 'No'],
                    defaultButton='Yes',
                    cancelButton='No',
                    dismissString='No')

                if result == 'No':
                    return False

            with open(full_file_path, 'w') as write_file:
                write_file.write(pretty_json)

            self.create_icon( kLibPose, pose_name + '.json' )

            print ('aniMeta: Pose written to ', full_file_path)

    def create_icon( self, *args ):

        section = args[0]
        name = args[1]

        path = self.get_path( section )

        size = 256

        ct = mc.currentTime( query = True )

        if not 'json' in name:
            mc.warning('aniMeta create icon: name needs png at the end')

        file_name = name.replace( 'json', 'png' )

        file_path = os.path.join( path, file_name )

        sel = mc.ls( sl=True )

        mc.select( cl=True )

        mc.playblast(
            orn = False,
            st = ct,
            et = ct,
            width = size*2,  # coz of retina on macbook pro?
            height = size*2,
            v = False,
            compression='png',
            quality=80,
            forceOverwrite = True,
            completeFilename = file_path,
            format = 'image'
        )
        mc.select( sel, r=True )

        self.refresh( section )

    def pose_item_ctx_menu(self, *args):
        self.item_ctx_menu( kLibPose, args[0], self.sender() )

    def anim_item_ctx_menu( self, *args ):
        self.item_ctx_menu( kLibAnim, args[ 0 ], self.sender() )

    def rig_item_ctx_menu( self, *args ):
        self.item_ctx_menu( kLibRig, args[ 0 ], self.sender() )

    def item_ctx_menu( self, *args ):

        section = args[0]
        QPos    = args[1]
        btn     = args[2]

        parentPosition = btn.mapToGlobal(QtCore.QPoint(0, 0))
        menuPosition = parentPosition + QPos

        self.menu.clear()

        if section == kLibPose:
            load_label   = 'Load Pose'
            delete_label = 'Delete Pose'
            rename_label = 'Rename Pose'
        if section == kLibAnim:
            load_label   = 'Load Animation'
            delete_label = 'Delete Animation'
            rename_label = 'Rename Animation'
        if section == kLibRig:
            load_label   = 'Load Rig Settings'
            delete_label = 'Delete Rig Settings'
            rename_label = 'Rename Rig Settings'

        item_name = btn.text() + '.json'

        if section == kLibRig:
            create_rig = QAction( self )
            create_rig.setText( 'Create Rig' )
            create_rig.triggered.connect( partial( self.create_item, section, item_name ) )
            self.menu.addAction( create_rig )

        import_pose = QAction( self )
        import_pose.setText( load_label )
        import_pose.triggered.connect( partial( self.import_item, section, item_name ) )
        self.menu.addAction( import_pose )


        rename_pose = QAction( self )
        rename_pose.setText( rename_label )
        rename_pose.triggered.connect( partial( self.rename_item, section, item_name ) )
        self.menu.addAction( rename_pose )

        delete_pose = QAction( self )
        delete_pose.setText( delete_label )
        delete_pose.triggered.connect( partial( self.delete_item, section, item_name ) )
        self.menu.addAction( delete_pose )

        self.menu.addSeparator()

        create_icon = QAction( self )
        create_icon.setText( "Create Icon" )
        create_icon.triggered.connect( partial( self.create_icon, section, item_name ) )
        self.menu.addAction( create_icon )

        self.menu.move(menuPosition)
        self.menu.show()

    def create_item(self, *args):
        section   = args[0]
        file      = args[1]
        path      = self.get_path( section )
        full_path = path+'/'+file

        with open(full_path, 'r') as read_file:
            data = read_file.read()

        data_dict = json.loads(data)

        rig_type = kBiped
        try:
            rig_type = kRigTypeString.index( data_dict['aniMeta'][0]['info']['rig_type'] )
        except:
            pass
        if section == kLibRig:
            rootNode = Char().create( name = 'Eve', type = rig_type  )

            try:
                ui = AniMetaUI( create=False )
                ui.char_list_refresh()

                # Select the new character
                ui.set_active_char( rootNode )
            except:
                pass

            self.import_doit( section, full_path )

    def pose_tree_ctx_menu(self, *args):
        self.tree_ctx_menu( kLibPose, args[0], self.sender() )

    def anim_tree_ctx_menu( self, *args ):
        self.tree_ctx_menu( kLibAnim, args[0], self.sender() )

    def rig_tree_ctx_menu( self, *args ):
        self.tree_ctx_menu( kLibRig, args[0], self.sender() )

    def tree_ctx_menu(self, *args):

        section = args[0]
        QPos    = args[1]
        btn     = args[2]

        parentPosition = btn.mapToGlobal(QtCore.QPoint(0, 0))
        menuPosition   = parentPosition + QPos

        self.menu.clear()

        add_folder = QAction( self )
        add_folder.setText( "Add Folder" )
        add_folder.triggered.connect( partial( self.add_folder, section  ) )
        self.menu.addAction( add_folder )

        rename_folder = QAction( self )
        rename_folder.setText( "Rename Folder" )
        rename_folder.triggered.connect( partial( self.rename_folder, section ) )
        self.menu.addAction( rename_folder )

        delete_folder = QAction( self )
        delete_folder.setText( "Delete Folder" )
        delete_folder.triggered.connect( partial( self.delete_folder, section ) )
        self.menu.addAction( delete_folder )

        self.menu.move(menuPosition)
        self.menu.show()

    def add_folder( self, section=kLibPose ):

        result = mc.promptDialog(
            title = 'New Folder',
            message = 'Enter Folder Name',
            button = [ 'OK', 'Cancel' ],
            defaultButton = 'OK',
            cancelButton = 'Cancel',
            dismissString = 'Cancel'
        )
        if result == 'OK':
            fileName = mc.promptDialog( query = True, text = True )

            path = self.get_path( section )

            new_path = os.path.join( path, fileName )

            if not os.path.isdir( new_path):
                try:
                    os.makedirs(new_path)
                except:
                    mc.warning('aniMeta: There was a problem creating the folder', new_path)

            if os.path.isdir( new_path):
                print('aniMeta: folder created successfully', new_path )

            self.tree_refresh( section )

    def rename_folder( self, section=kLibPose ):

        path = self.get_path( section )

        buff = os.path.split( path )

        result = mc.promptDialog(
            title = 'Rename Folder',
            text = buff[1],
            message = 'Enter Folder Name',
            button = [ 'OK', 'Cancel' ],
            defaultButton = 'OK',
            cancelButton = 'Cancel',
            dismissString = 'Cancel'
        )
        if result == 'OK':
            fileName = mc.promptDialog( query = True, text = True )

            new_path = os.path.join( buff[0], fileName)

            os.rename( path, new_path)

            self.tree_refresh( section )

    def delete_folder( self, section=kLibPose ):

        result = mc.confirmDialog(
            title = 'Delete Folder',
            message = 'Are you sure?\nThis operation is not undoable.',
            button = [ 'Yes', 'No' ],
            defaultButton = 'Yes',
            cancelButton = 'No',
            dismissString = 'No' )

        if result == 'Yes':
            try:
                path = self.get_path( section )
                shutil.rmtree( path )

                self.tree_refresh( section )
                self.refresh( )
            except:
                pass

    def rename_item( self, *args ):

        section = args[0]
        file    = args[1]
        path    = self.get_path( section )

        if '.json' in file:
            file = file.split('.')[0]

        if section == kLibPose:
            title_label = 'Delete Pose'
        elif section == kLibAnim:
            title_label = 'Delete Animation'
        elif section == kLibRig:
            title_label = 'Delete Rig Settings'


        result = mc.promptDialog(
            title = title_label,
            message = 'New Name',
            text = file,
            button = [ 'OK', 'Cancel' ],
            defaultButton = 'OK',
            cancelButton = 'Cancel',
            dismissString = 'Cancel'
        )
        if result == 'OK':
            fileName = mc.promptDialog( query = True, text = True )

            for suffix in ['json', 'png']:
                try:
                    src = os.path.join( path, file + '.' + suffix )
                    dst = os.path.join( path, fileName + '.' + suffix)
                    os.rename( src, dst )
                except:
                    pass

            self.refresh( section )

    def delete_item( self, *args ):

        section = args[0]
        file    = args[1]
        path    = self.get_path( section )

        if section == kLibPose:
            title_label = 'Delete Pose'
        elif section == kLibAnim:
            title_label = 'Delete Animation'
        elif section == kLibRig:
            title_label = 'Delete Rig Settings'

        result = mc.confirmDialog(
            title=title_label,
            message='Are you sure?\nThis operation is not undoable.',
            button=['Yes','No'],
            defaultButton='Yes',
            cancelButton='No',
            dismissString='No' )

        if result == 'Yes':

            file_path = os.path.join( path, file )

            self.delete_file( file_path )

            png_file_path = file_path.replace('json', 'png')

            self.delete_file( png_file_path )

            self.refresh( section )

    def delete_file(self, file):

        if os.path.isfile( file ):
            try:
                os.remove( file )
            except OSError as error:
                print ( str(error) )
            except:
                pass

    def import_item( self, *args, **kwargs ):

        section   = args[0]
        file      = args[1]
        path      = self.get_path( section )

        full_path = path+'/'+file

        self.import_doit( section, full_path )

    def import_doit( self, *args ):

        section   = args[0]
        full_path = args[1]

        if os.path.isfile(full_path):

            with open( full_path, 'r' ) as read_file:
                data = read_file.read()

            dict = json.loads( data )

            if 'aniMeta' in dict:

                data_type = None

                if 'data_type' in dict['aniMeta'][0]:
                    data_type = dict['aniMeta'][0]['data_type']

                    char = self.am.get_active_char()

                    if char is not None:

                        if data_type == 'aniMetaPose' and section == kLibPose:

                            self.rig.set_pose( dict )

                        elif data_type == 'aniMetaAnimation' and section == kLibAnim:

                            self.import_anim( char, dict )

                        elif data_type == 'aniMetaBiped' and section == kLibRig:

                            self.rig_import( char, dict )

                    else:
                        mc.warning( 'aniMeta load pose: please specify a character.' )

                else:
                    mc.warning('aniMeta load pose: file does not seem to be a valid pose file.')

            else:
                mc.warning( 'aniMeta load pose: file does not seem to be a valid aniMeta file.' )
        else:
            mc.warning('aniMeta load pose: invalid file specified', full_path)

# UI
# #
########################################################################################################################################################################################



    ####################################################################################################################
    #
    # Anim Import/Export


    def export_anim_dialog( self, *args, **kwargs ):

        char = self.am.get_active_char()

        if char is not None :

            self.anim_ui = 'aniMetaSaveAnimUI'

            if mc.window( self.anim_ui, exists=True ):
                mc.deleteUI( self.anim_ui )

            mc.window( self.anim_ui, title='Save Animation', w=200, h=100, rtf=True )

            mc.rowColumnLayout( numberOfColumns = 1, rs=[1,10], ro=[1,'top',10] )

            self.export_anim_name_ctrl = mc.textFieldGrp(  label='Animation Name' )

            row2 = mc.rowColumnLayout( numberOfColumns = 2, cs=[1,10] )
            mc.rowColumnLayout( row2, e=True,  cs = [ 2, 10 ] )

            mc.button( label = 'Save', width = 120, command = self.export_anim_doit )
            mc.button( label = 'Cancel', width = 120, command = partial( self.close_export_dialog, self.anim_ui ) )

            mc.showWindow()

        else:
            mc.warning( 'No Handles to export animation from.' )

    def close_export_dialog(selfself, *args ):
        if len(args):
            ui = args[0]
            if mc.window( ui, exists=True):
                mc.deleteUI( ui )

    def export_anim_doit( self, *args, **kwargs ):

        anim_name = mc.textFieldGrp( self.export_anim_name_ctrl, q=True, text=True )

        if mc.window( self.anim_ui, exists = True ):
            mc.deleteUI( self.anim_ui )

        char = self.am.get_active_char()

        if char is not None:

            nodes = Rig().get_char_handles( char, { 'Type': kHandle, 'Side': kAll } )
            sceneDict = self.am.get_scene_info()
            animDataDict = self.get_anim( nodes )

            animDict = { }

            animDict[ 'aniMeta' ] = [ { 'info': sceneDict, 'data_type': 'aniMetaAnimation' }, { 'data': animDataDict } ]

            pretty_json = json.dumps( animDict, indent=4, sort_keys=True)

            full_file_path = os.path.join( os.path.abspath(self.anim_path), anim_name + '.json' )

            with open(full_file_path, 'w') as write_file:
                write_file.write(pretty_json)

            self.create_icon( kLibAnim, anim_name + '.json' )

            self.refresh( kLibAnim )

            print( 'aniMeta: Animation written to ', full_file_path)

    def get_anim( self, nodes = [ ] ):
        dict = { }

        if len( nodes ) > 0:

            for node in nodes:
                if mc.objExists( node ):
                    dict[ node ] = self.get_attributes( node )
        return dict

    def get_attributes( self, node, getAnimKeys = True ):
        if mc.objExists( node ) == False:
            mc.warning( 'aniMeta getAttributes: object does not exist ', node )
            return None

        attrs = mc.listAttr( node, k = True ) or [ ]

        if mc.nodeType( node ) in [ 'transform', 'joint' ]:
            attrs.append( 'rotateOrder' )

        dict = { }

        if len( attrs ) > 0:

            for attr in attrs:
                attrDict = { }
                status = 0

                attrDict[ 'dataType' ] = mc.attributeQuery( attr, node = node, attributeType = True )

                con = mc.listConnections( node + '.' + attr, s = True, d = False ) or [ ]

                if len( con ) > 0:

                    if mc.nodeType( con ) in curveType:
                        attrDict[ 'input' ] = attrInput[ animCurve ]
                        # Either get the actual keyframe animation
                        if getAnimKeys:
                            attrDict[ 'animCurve' ] = self.get_anim_curve_data( con[ 0 ] )
                        # or just the animation node
                        else:
                            attrDict[ 'animCurve' ] = con[ 0 ]
                        status = animCurve

                    else:
                        attrDict[ 'input' ] = attrInput[ static ]
                        status = static

                else:
                    attrDict[ 'input' ] = attrInput[ static ]
                    status = static

                if status == static:

                    value = 0

                    if attrDict[ 'dataType' ] == 'enum':
                        value = mc.getAttr( node + '.' + attr, asString = True )
                    else:
                        value = mc.getAttr( node + '.' + attr )

                    if attrDict[ 'dataType' ] in floatDataTypes:
                        value = round( value, floatPrec )

                    if attrDict[ 'dataType' ] in angleDataTypes:
                        # gibt beim laden der pose nach dem guide mode falsche Rotationswerte,
                        # die ueberhaupt umgerechnet, sie wurden doch mit getAttr abgefragt
                        # value = round( math.degrees(value), floatPrec )
                        value = round( value, floatPrec )

                    attrDict[ 'value' ] = value

                if len( attrDict ) == 0:
                    attrDict = None

                dict[ attr ] = attrDict

        return dict

    def get_anim_curve_data( self, node ):
        dict = { }
        #try:
        animObj = self.am.get_mobject( node )
        if animObj is not None:
            animFn = oma.MFnAnimCurve( animObj )

            dict[ 'type' ] = curveType[ animFn.animCurveType ]

            # Pre Infinity Type
            if animFn.preInfinityType != oma.MFnAnimCurve.kConstant:
                dict[ 'pre' ] = animFn.preInfinityType

            # Post Infinity Type
            if animFn.postInfinityType != oma.MFnAnimCurve.kConstant:
                dict[ 'post' ] = animFn.postInfinityType

            if animFn.isWeighted:
                dict[ 'weighted' ] = animFn.isWeighted

            dict[ 'keys' ] = { }

            times = [ ]
            values = [ ]
            itt = [ ]  # In tangent type
            ott = [ ]  # Out tangent type
            itaw = [ ]  # In tangent angle Weight
            otaw = [ ]  # Out tangent angle weight
            itxy = [ ]  # In tangent XY
            otxy = [ ]  # Out tangent XY
            bd = [ ]    # breakdown
            wl = [ ]    # weights locked
            tl = [ ]    # tangents locked
            alt = [ ]
            for i in range( 0, animFn.numKeys ):
                time_tmp = round( animFn.input( i ).value, 5 )
                times.append( time_tmp )
                value_tmp = animFn.value( i )
                if dict[ 'type' ] == 'animCurveTA':
                    value_tmp = math.degrees( value_tmp )
                values.append( round( value_tmp, 5 ) )

                tmp_dict = { }
                itt.append( animFn.inTangentType( i ) )
                ott.append( animFn.outTangentType( i ) )

                itaw_tmp = animFn.getTangentAngleWeight( i, True )
                itaw.append( [ itaw_tmp[ 0 ].asDegrees(), itaw_tmp[ 1 ] ] )

                otaw_tmp = animFn.getTangentAngleWeight( i, False )
                otaw.append( [ otaw_tmp[ 0 ].asDegrees(), otaw_tmp[ 1 ] ] )

                itxy.append( animFn.getTangentXY( i, True ) )
                otxy.append( animFn.getTangentXY( i, False ) )

                bd.append( animFn.isBreakdown( i ) )
                wl.append( animFn.weightsLocked( i ) )
                tl.append( animFn.tangentsLocked( i ) )

                if itt[ i ] != oma.MFnAnimCurve.kTangentAuto:
                    tmp_dict[ 'itt' ] = itt[ i ]

                if ott[ i ] != oma.MFnAnimCurve.kTangentAuto:
                    tmp_dict[ 'ott' ] = itt[ i ]

                tmp_dict[ 'ia' ] = round( itaw[ i ][ 0 ], 5 )

                tmp_dict[ 'iw' ] = round( itaw[ i ][ 1 ], 5 )

                tmp_dict[ 'oa' ] = round( otaw[ i ][ 0 ], 5 )

                tmp_dict[ 'ow' ] = round( otaw[ i ][ 1 ], 5 )

                tmp_dict[ 'ix' ] = round( itxy[ i ][ 0 ], 5 )

                tmp_dict[ 'iy' ] = round( itxy[ i ][ 1 ], 5 )

                tmp_dict[ 'ox' ] = round( otxy[ i ][ 0 ], 5 )

                tmp_dict[ 'oy' ] = round( otxy[ i ][ 1 ], 5 )

                tmp_dict[ 'wl' ] = wl[ i ]

                tmp_dict[ 'l' ]  = tl[ i ]

                if len( tmp_dict ) > 0:
                    tmp_dict[ 'time' ] = times[ i ]

                    alt.append( tmp_dict )

            if len( alt ) > 0:
                dict[ 'keys' ][ 'tangent' ] = alt

            dict[ 'keys' ][ 'time' ] = times
            dict[ 'keys' ][ 'value' ] = values
        else:
            mc.warning('Can not get MObject for', node)

        return dict

    def import_anim( self, *args ):

        char = args[0]
        animDict = args[1]

        info = animDict[ 'aniMeta' ][ 0 ][ 'info' ]
        data = animDict[ 'aniMeta' ][ 1 ][ 'data' ]

        # flags = [ 'ia', 'iw', 'oa', 'ow', 'ix', 'iy', 'ox', 'oy' ]
        flags = [ 'ix', 'iy', 'ox', 'oy'  ]
        flags2 = [ 'l','wl', 'ia', 'iw', 'oa', 'ow'  ]

        cmds = ''
        for node in data.keys():
            for attr in data[ node ].keys():
                handle = self.am.find_node( char, node )
                if handle is None:
                    mc.warning('aniMeta: Can not find handle '+node)
                    continue
                if mc.objExists( handle + '.' + attr ):

                    node_attr_data = data[ node ][ attr ]
                    if node_attr_data[ 'input' ] == 'static':
                        pass
                    if node_attr_data[ 'input' ] == 'animCurve':
                        anim_data = node_attr_data[ 'animCurve' ]

                        # redundant?
                        type = anim_data[ 'type' ]


                        keys = anim_data[ 'keys' ]

                        if 'time' in keys and 'value' in keys:
                            times = keys[ 'time' ]
                            values = keys[ 'value' ]

                            if len( times ) == len( values ):

                                for i in range( len( times ) ):
                                    cmds += 'setKeyframe -time ' + str( times[ i ] ) + ' -value ' + str(
                                        values[ i ] ) + ' ' + handle + '.' + attr + ';\n'

                        if 'weighted' in anim_data:
                            if anim_data[ 'weighted' ]:
                                weighted = 'true'
                            else:
                                weighted = 'false'
                        else:
                            weighted = 'false'
                        cmds += 'keyTangent -e -weightedTangents ' + weighted +  ' -animation objects ' + handle + '.' + attr + ';\n'

                        if 'tangent' in keys:
                            tangents = keys[ 'tangent' ]

                            for tangent in tangents:
                                if 'time' in tangent:
                                    # if weighted:
                                    #   cmds += 'keyTangent -e -a -t '+ tangent['time'] + ' -at ' + attr + ' -wt 1 ' + node + ';\n'

                                    kt = 'keyTangent  -e -a -t ' + str( tangent[ 'time' ] ) + ' -at ' + attr

                                    for flag in flags:
                                        if flag in tangent:
                                            kt += ' -' + flag + ' ' + str( tangent[ flag ] )

                                    kt += ' ' + handle + ';\n'
                                    cmds += kt

                                    if weighted == 'true':
                                        kt = 'keyTangent  -e -a -t ' + str( tangent[ 'time' ] ) + ' -at ' + attr

                                        for flag in flags2:
                                            if flag in tangent:
                                                if flag == 'wl' or flag == 'l':
                                                    kt += ' -' + flag + ' ' + str( int( tangent[ flag ] )  )
                                                else:
                                                    kt += ' -' + flag + ' ' + str( tangent[ flag ] )

                                        kt += ' ' + handle + ';\n'
                                        cmds += kt

                else:
                    mc.warning( 'aniMeta: Can not find object ' + node + '.' + attr + ', skipping...' )

        if len( cmds ):
            mc.undoInfo( openChunk=True )
            mm.eval( cmds )
            mc.undoInfo( closeChunk=True )
            print ('aniMeta: file imported.')

    # Anim Import/Export
    #
    ####################################################################################################################

    ####################################################################################################################
    #
    # Rig Import/Export


    def rig_export_dialog( self, *args, **kwargs ):

        char = self.am.get_active_char()

        if char is not None :

            self.rig_ui = 'aniMetaSaveRigUI'

            if mc.window( self.rig_ui, exists=True ):
                mc.deleteUI( self.rig_ui )

            mc.window( self.rig_ui, title='Save Rig Settings', w=200, h=100, rtf=True )

            mc.rowColumnLayout( numberOfColumns = 1, rs=[1,10], ro=[1,'top',10] )

            self.rig_export_name_ctrl = mc.textFieldGrp(  label='Settings Name' )

            row2 = mc.rowColumnLayout( numberOfColumns = 2, cs=[1,10] )
            mc.rowColumnLayout( row2, e=True,  cs = [ 2, 10 ] )

            mc.button( label = 'Save', width = 120, command = self.rig_export_doit )
            mc.button( label = 'Cancel', width = 120, command = partial( self.close_export_dialog, self.rig_ui )  )

            mc.showWindow()

        else:
            mc.warning( 'No Handles to export animation from.' )


    def rig_export_doit( self, *args, **kwargs ):

        rig_name = mc.textFieldGrp( self.rig_export_name_ctrl, q=True, text=True )

        if mc.window( self.rig_ui, exists = True ):
            mc.deleteUI( self.rig_ui )

        char = self.am.get_active_char()

        if char is not None:

            metaData = self.am.get_metaData( char )

            rigState = None
            rig = Rig()

            if 'RigState' in metaData:
                rigState = metaData[ 'RigState' ]
            else:
                mc.warning( 'aniMeta: unable to determine the rig`s status, aborting export process.' )
                return False

            if rigState != kRigStateControl:
                mc.warning( 'aniMeta: To export a rig, please put it in control mode.' )
            else:
                char_data = { }

                char_data[ 'root' ] = { }
                char_data[ 'handles' ] = { }
                char_data[ 'joints' ] = { }

                for attr in mc.listAttr( char, k = True ) or [ ]:
                    char_data[ 'root' ][ attr ] = mc.getAttr( char + '.' + attr )

                handles = rig.get_char_handles( char, { 'Type': kHandle, 'Side': kAll } ) or [ ]

                if len( handles ) > 0:

                    joint_grp = self.am.find_node( char, 'Joint_Grp' ) or [ ]
                    joints = mc.listRelatives( joint_grp, c = True, ad = True, typ = 'joint', pa=True )
                    attrs = [ 'controlSize', 'controlSizeX', 'controlSizeY', 'controlSizeZ', 'controlOffset', 'controlOffsetX', 'controlOffsetY', 'controlOffsetZ' ]

                    for handle in handles:

                        tmp = { }
                        handle_path = self.am.find_node( char, handle )

                        tmp[ 'data' ] = mc.getAttr( handle_path + '.aniMetaData' )

                        for attr in attrs:
                            try:
                                tmp[ attr ] = round( mc.getAttr( handle_path + '.' + attr ), 4 )
                            except:
                                pass

                        char_data[ 'handles' ][ self.am.short_name(handle) ] = tmp

                    for joint in joints:

                        joint_path = self.am.find_node( char, joint )

                        tmp = { }

                        for attr in [ 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'jox', 'joy', 'joz' ]:

                            value = mc.getAttr( joint_path + '.' + attr )

                            tmp[ attr ] = value
                        if len( tmp ) > 0:
                            char_data[ 'joints' ][ self.am.short_name(joint)  ] = tmp

                    sceneDict = self.am.get_scene_info()

                    sceneDict['rig_type'] = kRigTypeString[metaData['RigType']]

                    aniMetaDict = { }

                    aniMetaDict[ 'aniMeta' ] = [ { 'info': sceneDict, 'data_type': 'aniMetaBiped' }, { 'data': char_data } ]

                    pretty_json = json.dumps( aniMetaDict, indent = 4, sort_keys = True )

                    full_file_path = os.path.join( os.path.abspath( self.rig_path ), rig_name + '.json' )

                    with open( full_file_path, 'w' ) as write_file:
                        write_file.write( pretty_json )

                    self.create_icon( kLibRig, rig_name + '.json' )

                    self.refresh( kLibRig )

                    print ('aniMeta: Rig exported to ', full_file_path)
                else:
                    print ('aniMeta: Nothing to export, please select or specify nodes.')


    def rig_export(self, char, fileName):

        metaData = self.am.get_metaData(char)

        rigState = None
        rig = Rig()

        if 'RigState' in metaData:
            rigState = metaData['RigState']
        else:
            mc.warning('aniMeta: unable to determine the rig`s status, aborting export process.')
            return False

        if rigState != kRigStateControl:
            mc.warning('aniMeta: To export a rig, please put it in control mode.')
        else:
            char_data = {}

            char_data['root'] = {}
            char_data['handles'] = {}
            char_data['joints'] = {}

            for attr in mc.listAttr(char, k=True) or []:
                char_data['root'][attr] = mc.getAttr(char + '.' + attr)

            handles = rig.get_char_handles( char, {'Type': kHandle, 'Side': kAll}) or []

            if len(handles) > 0:

                joint_grp = self.am.find_node(char, 'Joint_Grp') or []
                joints = mc.listRelatives(joint_grp, c=True, ad=True, typ='joint', pa=True)
                attrs = ['controlSize', 'controlSizeX', 'controlSizeY', 'controlSizeZ', 'controlOffset', 'controlOffsetX', 'controlOffsetY', 'controlOffsetZ']

                for handle in handles:

                    tmp = {}

                    tmp['data'] = mc.getAttr(handle + '.aniMetaData')

                    for attr in attrs:
                        try:
                            tmp[attr] = round(mc.getAttr(handle + '.' + attr), 4)
                        except:
                            pass

                    char_data['handles'][handle] = tmp

                for joint in joints:

                    tmp = {}

                    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'jox', 'joy', 'joz']:
                        value = round(mc.getAttr(joint + '.' + attr), 4)
                        tmp[attr] = value

                    if len(tmp) > 0:
                        char_data['joints'][joint] = tmp

                sceneDict = self.am.get_scene_info()

                sceneDict['rig_type'] = kRigTypeString[metaData['RigType']]

                aniMetaDict = {}

                aniMetaDict['aniMeta'] = [{'info': sceneDict, 'type': 'biped_rig'}, {'data': char_data}]

                jsonDictData = json.dumps(aniMetaDict, indent=4, sort_keys=True)

                f = open(fileName, 'w')
                f.write(jsonDictData)
                f.close()
                return True
            else:
                print ('aniMeta: Nothing to export, please select or specify nodes.')

    def rig_import( self, *args ):

        char = args[ 0 ]
        dict = args[ 1 ]

        info = dict[ 'aniMeta' ][ 0 ][ 'info' ]
        data = dict[ 'aniMeta' ][ 1 ][ 'data' ]

        type = kBiped
        if 'rig_type' in info:
            type = kRigTypeString.index(info['rig_type'])

        _rig_   = Rig()
        _char_  = Char()
        _biped_ = Biped()

        metaData = self.am.get_metaData(char)
        rigState = None

        if 'RigState' in metaData:

            mc.undoInfo( openChunk=True )

            mc.progressWindow()

            rigState = metaData['RigState']

            if rigState == kRigStateControl:

                _char_.toggle_guides()

            mc.progressWindow( e = True, pr = 10 )

            _char_.delete_body_guides( char )

            mc.progressWindow( e = True, pr = 20 )

            ###############################################################################
            #
            #   Reset joints to default and apply data from dict

            if 'joints' in data:

                for key in sorted(data['joints'].keys()):

                    if not 'Blend' in key and not 'Aux' in key:

                        joint = self.am.find_node(char, key)

                        if joint is not None:

                            for attr in sorted(data['joints'][key].keys()):

                                # Translates need to be set via the multiply node on the parent
                                try:
                                    value = data['joints'][key][attr]
                                    mc.setAttr(joint + '.' + attr, value )
                                except:
                                    mc.warning('aniMeta: There is a problem setting attribute', attr,  'on joint', joint)
                                    pass
                        else:
                            mc.warning('aniMeta: Can not find joint', key)
            #   Reset joints to default and apply data from dict
            #
            ###############################################################################

            mc.progressWindow( e = True, pr = 30 )

            # Set Root Attributes
            if 'root' in data:

                rootDict = data['root']

                for attr in rootDict.keys():

                    if mc.attributeQuery(attr, node=char, exists=True):
                        try:
                            mc.setAttr(char + '.' + attr, rootDict[attr])
                        except:
                            pass

            mc.progressWindow( e = True, pr = 40 )
            mm.eval('dgdirty -a;')

            # Build the guides so they match the joints
            # The guides are needed for building the control rig
            _char_.build_body_guides( char, type )

            mc.progressWindow( e = True, pr = 60 )

            # Build the control rig
            _biped_.build_control_rig( char )

            mc.progressWindow( e = True, pr = 80 )

            _biped_.build_mocap( char, type )

            if 'handles' in data:

                handleDict = data['handles']

                attrs = ['controlSize', 'controlSizeX', 'controlSizeY', 'controlSizeZ', 'controlOffset', 'controlOffsetX', 'controlOffsetY', 'controlOffsetZ']

                for handle in sorted( handleDict ):

                    handle_path = self.am.find_node( char, handle )

                    if handle_path is None:
                        mc.warning('aniMeta import rig: can not find handle', handle )
                        continue
                    else:
                        for attr in attrs:
                            if attr in handleDict[handle]:
                                try:
                                    if handle is not None:
                                        mc.setAttr( handle_path + '.' + attr, handleDict[handle][attr])
                                except:
                                    pass

            mc.progressWindow( e = True, pr = 90 )

            mc.setAttr( char + '.show_Rig', True )
            mc.setAttr( char + '.show_Guides', False)

            self.am.update_ui()

            om.MGlobal.displayInfo('aniMeta: Rig preset loaded successfully.')

            mc.progressWindow( ep = True )

            mc.undoInfo( closeChunk=True )

    # Rig Import/Export
    #
    ####################################################################################################################

class aniMetaTreeWidget( QTreeWidget):
    def __init__(self, parent = None):
        QTreeWidget.__init__(self, parent)

    def mousePressEvent (self, event):

        if event.button() == QtCore.Qt.LeftButton:
            self.selected()

        QTreeWidget.mousePressEvent(self, event)

    def selected( self ):

        if self.currentItem() is not None:
            tree = self.currentItem().treeWidget()

            iterator = QTreeWidgetItemIterator( self )

            # Remove empty lines that keep showing up when selecting an item with children
            while iterator.value():
                item = iterator.value()
                if item.text(0) == '':
                    parent = item.parent()
                    parent.removeChild( item )
                    parent.removeChild( item )
                iterator += 1

    def get_index( self, item ):
        index = self.indexFromItem( item )
        return index

class aniMetaLibItem( QPushButton ):

    def __init__(self, *args):
        QPushButton.__init__(self, *args)

    def mouseDoubleClickEvent(self, event):

        path = mc.optionVar( q= 'aniMeta_lib_pose_path' )

        if event.button() == QtCore.Qt.LeftButton:

            full_path = os.path.join( path, self.text()+'.json' )

            if os.path.isfile( full_path ):
                lib = LibTab()
                lib.import_doit( kLibPose, full_path )
            else:
                mc.warning('aniMeta pose import: invalid path', full_path )

    def mousePressEvent (self, event):
        pass


class AniMetaOptionsUI():

    # the UI name for Maya
    name = 'aniMetaOptionsUI'

    def __init__( self, *args, **kwargs ):

        # Offset between items in the layout
        self.offset = 4

        self.__ui__()

    def __ui__( self ):

        # Delete window, if exists
        if mc.window( self.name, exists = True ):
            mc.deleteUI( self.name )

        # Create Window
        mc.window( self.name, title = 'aniMeta Options', w = 300, h = 400 )

        ################################################################################################
        # Menu
        mc.menuBarLayout()

        self.edit_menu = mc.menu( 'Settings' )

        mc.menuItem( 'Save Settings', command = self.save_settings )
        mc.menuItem( 'Reset Settings' )

        # Menu
        ################################################################################################

        # The main layout to arrange things
        self.form = mc.formLayout()

        # Useful for resizable UIs
        self.scroll = mc.scrollLayout( cr = True )

        # Picker section
        mc.frameLayout( label = 'Picker UI' )

        self.picker_btn_size = mc.optionMenuGrp( label = 'Button Size', cc = self.change_picker_button )

        main_tab =  MainTab()

        for item in main_tab.get_button_options():
            mc.menuItem( label = item )


        self.save_button = mc.button( label = 'Save', parent = self.form, command=self.save_settings)
        self.cancel_button = mc.button( label = 'Cancel', parent = self.form, command=self.delete_ui  )

        mc.formLayout(
            self.form, e = True,
            af = [
                (self.save_button, 'bottom', self.offset),
                (self.save_button, 'left', self.offset)
            ],
            ap = [ (self.save_button, 'right', self.offset * 0.5, 50) ]
        )

        mc.formLayout(
            self.form, e = True,
            af = [
                (self.cancel_button, 'bottom', self.offset),
                (self.cancel_button, 'right', self.offset)
            ],
            ap = [ (self.cancel_button, 'left', self.offset * 0.5, 50) ]
        )

        mc.formLayout(
            self.form, e = True,
            af = [ (self.scroll, 'left', self.offset),
                   (self.scroll, 'right', self.offset),
                   (self.scroll, 'top', 0),
                   (self.scroll, 'bottom', 48)
                   ] )

        self.refresh_ui()
        mc.showWindow()

    def reset_settings( self ):

        # Picker button size
        mc.optionVar( sv = [ 'aniMetaUIButtonSize', 'Medium' ] )


    def save_settings( self, *args ):

        value = mc.optionMenuGrp( self.picker_btn_size, query = True, value = True )

        mc.optionVar( sv = [ 'aniMetaUIButtonSize', value ] )

    def refresh_ui( self ):

        button_size = 'Medium'
        if mc.optionVar( exists = 'aniMetaUIButtonSize' ):
            button_size = mc.optionVar( query = 'aniMetaUIButtonSize' )
        else:
            mc.optionVar( sv=('aniMetaUIButtonSize', button_size))

        mc.optionMenuGrp( self.picker_btn_size, edit=True, value=button_size )


    def delete_ui (self, *args):
        mc.deleteUI( self.name )

    def change_picker_button( self, *args ):
        self.save_settings()

        AniMeta().update_ui( picker = True )

class BlendShapeSplitter():

    ui_name = 'blendShapeSplitterUI'
    ui_title = 'aniMeta BlendShape Splitter'

    def __init__(self, *args, **kwargs):

        self.base_geo  = None
        self.blend_geo = None
        self.guide_geo = None

        self.base_default_text  = 'Please specify a base mesh.'
        self.blend_default_text = 'Please specify a blendShape mesh.'
        self.guide_default_text = 'Please specify a guide object.'

        self.ui()

        sel = mc.ls(sl=True)
        if len( sel ) == 2:
            mc.select( sel[0], r=True )
            self.getBase()
            mc.select( sel[1], r=True )
            self.getBlend()
            mc.select( sel, r=True )

    def ui(self):

        if mc.window( self.ui_name, exists=True ):
            mc.deleteUI( self.ui_name )

        mc.window( self.ui_name, w=368, h=242,  sizeable=False, t=self.ui_title )

        mc.scrollLayout( cr=True )

        mainForm = mc.formLayout( )

        blendFrame = mc.frameLayout( l='Meshes', li=5, la='center', cl=False, cll=True )

        blendForm = mc.formLayout( )

        self.base_ctrl = mc.textFieldButtonGrp(
            adj=2,
            bc= partial( self.getBase ) ,
            cat=[1,'left',0],
            cw3=[75,175,30],
            label='Base Shape',
            text=self.base_default_text ,
            buttonLabel='Get',
            ann=self.base_default_text ,
            ed=False
        )
        self.blend_ctrl = mc.textFieldButtonGrp(
            adj=2,
            bc= partial( self.getBlend  ) ,
            cc='jbBlendSplitterCheck',
            cat=[1,'left',0],
            cw3=[75,175,30],
            label='Blend Shape',
            text=self.blend_default_text,
            buttonLabel='Get',
            ann=self.blend_default_text,
            ed=False
        )
        mc.formLayout (
            blendForm,
            edit=True,
            af=(
                ( self.base_ctrl, 'left', 16 ),
                ( self.base_ctrl, 'top', 0 ),
                ( self.base_ctrl, 'right', 16 ),
                ( self.blend_ctrl, 'left', 16 ),
                ( self.blend_ctrl, 'right', 16 )
            ),
            ac=(
                ( self.blend_ctrl, 'top', 8, self.base_ctrl )
            )
        )
        guideFrame = mc.frameLayout( l='Guide Object', li=5, la='center', cl=False, cll=True,p=mainForm )

        self.guideForm = mc.formLayout( )

        self.guide_ctrl = mc.textFieldButtonGrp(
            adj=2,
            bc=self.createGuide,
            cat=[1,'left',0],
            cw3=[75,175,30],
            label='Blend Guide',
            text=self.guide_default_text,
            buttonLabel='Get',
            ann=self.guide_default_text,
            ed=False
        )
        self.guide_scale_ctrl = mc.attrFieldSliderGrp(
            adj=3,
            cat=(1,'left',0),
            cw3=(75,50,157 ),
            label= 'Blend Width',
            min=0.0001,
            max=1.0
        )
        self.blend_btn_1 = mc.button(
            label = 'Toggle Visibility',
            c = self.toggleGuideVis
        )
        self.blend_btn_2 = mc.button(
            label = 'Delete Guide',
            c = self.deleteGuide
        )
        mc.formLayout (
            self.guideForm,
            edit=True,
            af=(
                ( self.guide_ctrl, 'left', 16 ),
                ( self.guide_ctrl, 'top', 0 ),
                ( self.guide_ctrl, 'right', 16 ),
                ( self.guide_scale_ctrl, 'left', 16 ),
                ( self.guide_scale_ctrl, 'right', 16 ),
                ( self.blend_btn_1, 'left', 16 ),
                ( self.blend_btn_2, 'right', 16 )
            ),
            ac=(
                ( self.guide_scale_ctrl, 'top', 8,  self.guide_ctrl),
                ( self.blend_btn_1, 'top', 8, self.guide_scale_ctrl ),
                ( self.blend_btn_2, 'top', 8, self.guide_scale_ctrl )
            ),
            ap=(
                ( self.blend_btn_1, 'right', 4, 50 ),
                ( self.blend_btn_2, 'left', 4, 50 )
            )
        )
        self.splitButton = mc.button( 'Split BlendShape', c=self.split, h=26, p=mainForm )

        mc.formLayout(
            mainForm,
            edit=True,
            af=(
                ( blendFrame, 'left', 0 ),
                ( blendFrame, 'top', 0 ),
                ( blendFrame, 'right', 0 ),
                ( guideFrame, 'left', 0 ),
                ( guideFrame, 'right', 0 ),
                ( self.splitButton, 'left', 8 ),
                ( self.splitButton, 'right', 8 )
            ),
            ac=(
                ( guideFrame, 'top', 8, blendFrame ),
                ( self.splitButton, 'top', 8, guideFrame )
            )
        )
        self.refresh_ui()
        mc.showWindow()

    def shortName( self, name ):
        if '|' in name:
            buff = name.split( '|' )
            return buff[len(buff)-1]
        else:
            return name

    def getBase( self, *args  ):

        objs = mc.ls( sl=True, l=True )

        if len( objs ):
            shapes = mc.listRelatives( objs[0], pa=True, s=True )
            if ( shapes ):
                if mc.nodeType( shapes[0] ) == 'mesh':

                    self.base_geo = objs[0]
                    short = self.shortName( self.base_geo )
                    mc.textFieldButtonGrp(
                        self.base_ctrl,
                        e=True,
                        tx=short
                    )
                    self.createGuide()
                    mc.select( objs, r=True )


    def getBlend(self, *args):

        sel = mc.ls(sl=True)

        if sel:
            if len( sel ) == 1:
                shapes = mc.listRelatives( sel[0], pa=True, s=True )
                if shapes:
                    if mc.nodeType( shapes[0] ) == 'mesh':
                        self.blend_geo = sel[0]
                        short = self.shortName( self.blend_geo )
                        mc.textFieldButtonGrp ( self.blend_ctrl, e=True, text=short )
                        self.refresh_ui()
                        mc.select( sel, r=True )

            else:
                mc.warning('Please select only one mesh.')

    def createGuide(self):
        obj = self.base_geo
        if obj:
            if mc.objExists( obj ):

                sel = mc.ls(sl=True)

                box = mc.exactWorldBoundingBox( obj )
                name = self.shortName( obj ) + '_BlendGuide'

                scale = 0.5

                if mc.objExists( name ):
                    scale = mc.getAttr( name + '.sx')
                    mc.delete( name )

                plane = mc.polyPlane(
                    name=name,
                    ax=(0,0,1),
                    sx=1,
                    sy=1,
                    w=(box[3]-box[0]),
                    h=(box[4]*2),
                    ch=False
                )
                self.guide_geo = plane[0]

                shape = mc.listRelatives( plane, pa=True, s=True )[0]

                t0 = mc.xform( plane[0] + '.vtx[0]', q=True, ws=True, t=True )
                t1 = mc.xform( plane[0] + '.vtx[1]', q=True, ws=True, t=True )

                mc.xform( plane[0] + '.vtx[0]',  ws=True, t=(t0[0], box[1], t0[2]) )
                mc.xform( plane[0] + '.vtx[1]',  ws=True, t=(t1[0], box[1], t1[2]) )

                parent = mc.listRelatives( self.base_geo, pa=True, p=True )

                if parent:
                    plane[0] = mc.parent( plane[0], parent[0] )[0]
                    t = mc.getAttr( self.base_geo + '.t')
                    mc.setAttr( plane[0] + '.t', t[0][0], t[0][1], t[0][2] )

                mc.xform( plane[0], ws=True, r=True, t=(0,0,box[5]+0.01))
                mc.parentConstraint( self.base_geo, plane[0], mo=True )

                mc.select( cl=True )

                for i in range( 4 ):
                    for x in 'xyz':
                        mc.setAttr( shape + '.pt[' + str(i) + '].p' + x, l=True )

                # Lock Topology
                mc.setAttr( shape + '.allowTopologyMod', 0 )
                mc.setAttr( shape + '.overrideEnabled', 1 )
                mc.setAttr( shape + '.overrideDisplayType', 2 )

                # Define Material names
                mat = 'blendMat'
                matSG = 'blendMatSG'

                # Create Shader if it doesn`t exist
                if not mc.objExists(matSG):
                    mat = mc.shadingNode( 'lambert', asShader=True , name= mat )
                    matSG = mc.sets( renderable=True, empty=True, noSurfaceShader=True, name=matSG )
                    mc.connectAttr( mat + '.outColor', matSG + '.surfaceShader' )
                mc.sets(shape, fe=matSG)

                # Set Shader Color and Transparency
                mc.setAttr( mat + '.color', 0.175, 0.3, 0.5, type='double3' )
                mc.setAttr( mat + '.transparency', 0.5, 0.5, 0.5, type='double3' )

                mc.setAttr( self.guide_geo + '.sx', scale)

                for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz',  'sy', 'sz' ]:
                    mc.setAttr( self.guide_geo + '.' + attr, l=True, k=False )

                mc.attrFieldSliderGrp( self.guide_scale_ctrl, e=True, at=self.guide_geo + '.sx'  )
                mc.textFieldButtonGrp( self.guide_ctrl, e=True, text=self.guide_geo )

                self.refresh_ui()
                mc.select( sel, r=True )

    def split(self, *args):

        if self.blend_geo and self.guide_geo and self.base_geo:

            if mc.objExists( self.base_geo ) and  mc.objExists(self.blend_geo) and mc.objExists(self.guide_geo):

                sel = mc.ls(sl=True)

                t0 = mc.xform( self.guide_geo+'.vtx[0]', q=True,  os=True, t=True )
                t1 = mc.xform( self.guide_geo+'.vtx[1]', q=True,  os=True, t=True )

                maxX = t1[0] * mc.getAttr( self.guide_geo + '.sx' )
                minX = t0[0] * mc.getAttr( self.guide_geo + '.sx' )

                c = mc.polyEvaluate( self.base_geo, v=True)
                count = c

                positive = []
                negative = []
                inside   = []

                for i in range( count ):
                    t = mc.xform( self.base_geo + '.vtx['+str(i) + ']', q=True, a=True, os=True, t=True)
                    x = round( t[0], 5 )

                    if x > maxX:
                        positive.append( i )
                    elif x < minX:
                        negative.append( i )
                    elif x >= minX and x <= maxX:
                        inside.append( i )
                    else:
                        mc.warning( 'Invalid case for vertex', i )

                left  = None
                right = None

                blend_L = self.blend_geo + '_Lft'
                blend_R = self.blend_geo + '_Rgt'

                if not mc.objExists( blend_L ):
                    left = mc.duplicate( self.base_geo )[0]
                    blend_L = self.shortName(blend_L)
                    left = mc.rename( left, blend_L )
                else:
                    left = blend_L

                if not mc.objExists(blend_R):
                    right = mc.duplicate(self.base_geo)[0]
                    blend_R = self.shortName(blend_R)
                    right = mc.rename( right, blend_R )
                else:
                    right = blend_R

                for i in range( len ( positive )):
                    tr = mc.xform( self.blend_geo + '.vtx['+str(positive[i]) + ']', q=True, os=True, t=True, a=True )
                    mc.xform ( left  + '.vtx['+str(positive[i]) + ']', a=True, os=True, t=tr )

                for i in range(len(positive)):
                    tr = mc.xform(self.base_geo + '.vtx[' + str(negative[i]) + ']', q=True, os=True, t=True, a=True)
                    mc.xform( left + '.vtx[' + str(negative[i]) + ']', a=True, os=True, t=tr)

                for i in range( len ( negative )):
                    tr = mc.xform( self.blend_geo + '.vtx['+str(negative[i]) + ']', q=True, os=True, t=True, a=True )
                    mc.xform ( right  + '.vtx['+str(negative[i]) + ']', a=True, os=True, t=tr )

                for i in range(len(negative)):
                    tr = mc.xform(self.base_geo + '.vtx[' + str(positive[i]) + ']', q=True, os=True, t=True, a=True)
                    mc.xform( right + '.vtx[' + str(positive[i]) + ']', a=True, os=True, t=tr)

                for i in range( len( inside ) ):
                    t      = mc.xform( self.base_geo  + '.vtx['+str(inside[i]) + ']', q=True, os=True, t=True, a=True )
                    blendT = mc.xform( self.blend_geo + '.vtx['+str(inside[i]) + ']', q=True, os=True, t=True, a=True )

                    x = round ( t[0], 5 )

                    clamp = ( x + maxX ) / ( maxX * 2 )
                    val = self.clamp( clamp, 0, 1 )
                    val = -90 + ( val * 180 )
                    val = math.sin( math.radians( val ))
                    val = ( val + 1 ) / 2

                    valX = (( 1-val ) * t[0]) + (val * blendT[0])
                    valY = (( 1-val ) * t[1]) + (val * blendT[1])
                    valZ = (( 1-val ) * t[2]) + (val * blendT[2])

                    mc.xform( left + '.vtx[' + str(inside[i]) + ']', a=True, os=True, t=[valX, valY, valZ])

                    valX = (val  * t[0]) + (( 1-val ) * blendT[0])
                    valY =  (val  * t[1]) + (( 1-val ) * blendT[1])
                    valZ =  (val  * t[2]) + (( 1-val ) * blendT[2])

                    mc.xform( right + '.vtx[' + str(inside[i]) + ']', a=True, os=True, t=[valX, valY, valZ])

                bb = mc.exactWorldBoundingBox( self.blend_geo )
                height = abs( bb[1] - bb[4] )
                pos2 = mc.xform ( self.blend_geo, q=True, a=True, ws=True, t=True )

                for x in 'xyz':
                    for node in [ blend_L, blend_R]:
                        mc.setAttr( node + '.t'+x, l=False )
                        mc.xform( node, ws=True, a=True, t=pos2)

                # Move the blends down
                mc.xform( blend_L, r=True, t=[0,height*-1.1,0] )
                mc.xform( blend_R, r=True, t=[0,height*-2.2,0] )

                print( 'Blendshapes split successfully: ' + self.shortName(blend_L) +', '+ self.shortName(blend_R) )

                mc.select( sel, r=True )
            else:
                if not mc.objExists( self.base_geo ):
                    mc.warning('Can not find blend ' + self.base_geo )
                if not mc.objExists( self.blend_geo ):
                    mc.warning('Can not find base ' + self.base_geo )
                if not mc.objExists( self.guide_geo ):
                    mc.warning('Can not find guide ' + self.guide_geo )

        else:
            print ('Please specify all necessary objects.')

    def clamp(self, value, minValue, maxValue):
        if value < minValue:
            return minValue
        elif value > maxValue:
            return maxValue
        else:
            return value

    def toggleGuideVis(self, *args):
        if mc.objExists( self.guide_geo ):
            v = mc.getAttr( self.guide_geo + '.v' )
            mc.setAttr( self.guide_geo+'.v', 1-v )

    def deleteGuide(self, *args):
        if mc.objExists( self.guide_geo ):
            mc.delete( self.guide_geo)
            self.guide_geo = None
        self.refresh_ui()

    def refresh_ui(self,*args):

        if self.base_geo:
            mc.optionVar( sv=('aniMetaBlendSplitBase', self.base_geo) )
        else:
            if mc.optionVar(  exists='aniMetaBlendSplitBase' ):
                self.base_geo = mc.optionVar( query='aniMetaBlendSplitBase'  )

        if self.blend_geo:
            mc.optionVar( sv=('aniMetaBlendSplitBlend', self.blend_geo) )
        else:
            if mc.optionVar(  exists='aniMetaBlendSplitBlend' ):
                self.blend_geo = mc.optionVar( query='aniMetaBlendSplitBlend'  )

        # Check if base obj exists and update control and guide
        if self.base_geo:
            if mc.objExists(self.base_geo) :
                mc.textFieldButtonGrp( self.base_ctrl, e=True, text=self.shortName(self.base_geo) )
                if not self.guide_geo:
                    self.createGuide()
        if self.blend_geo:
            if mc.objExists(self.blend_geo) :
                mc.textFieldButtonGrp( self.blend_ctrl, e=True, text=self.shortName(self.blend_geo) )

        # Lock stuff if it isn`t available
        if not self.guide_geo:
            mc.textFieldButtonGrp( self.guide_ctrl, e=True, text=self.guide_default_text)
            mc.button( self.splitButton, e=True, en=False )
            mc.button( self.blend_btn_1, e=True, en=False )
            mc.button( self.blend_btn_2, e=True, en=False )
            mc.attrFieldSliderGrp( self.guide_scale_ctrl, e=True, en=False )
        else:
            mc.textFieldButtonGrp( self.guide_ctrl, e=True, text=self.shortName( self.guide_geo) )
            mc.button( self.splitButton, e=True, en=True )
            mc.button( self.blend_btn_1, e=True, en=True )
            mc.button( self.blend_btn_2, e=True, en=True )
            mc.attrFieldSliderGrp( self.guide_scale_ctrl, e=True, en=True, at=self.guide_geo+'.sx' )

        # Suppress the split button as long as one of the components is missing
        if not self.blend_geo or not self.base_geo or not self.guide_geo:
            mc.button( self.splitButton, e=True, en=False )
        else:
            mc.button( self.splitButton, e=True, en=True )


class Orient_Transform_UI():

    def __init__(self, *args):

        self.ui_name = 'aniMeta_Orient_Transform_UI'

        self.create_ui()

    def create_ui(self):

        if mc.window(self.ui_name, exists=True):
            mc.deleteUI(self.ui_name)

        win = mc.window(self.ui_name, w=200, h=100, title='Orient Transform', sizeable=False)

        layout = mc.rowColumnLayout(nc=1)

        frame1 = mc.frameLayout(parent=layout, bv=True, nbg=True, labelAlign='center', label='Aim Vector')
        self.rg1 = mc.radioButtonGrp(l='Axis', labelArray3=['X', 'Y', 'Z'], numberOfRadioButtons=3,
                                     cw4=[100, 30, 30, 30], sl=1)

        self.cb1 = mc.checkBoxGrp(l='Invert Aim', cw2=[100, 30])

        frame2 = mc.frameLayout(parent=layout, bv=True, nbg=True, labelAlign='center', label='Up Vector')
        self.rg2 = mc.radioButtonGrp(l='Axis', labelArray3=['X', 'Y', 'Z'], numberOfRadioButtons=3,
                                     cw4=[100, 30, 30, 30], sl=2)

        self.cb2 = mc.checkBoxGrp(l='Invert Up', cw2=[100, 30])
        self.cb3 = mc.checkBoxGrp(l='Use Up Vec Object', cw2=[100, 30], cc=self.toggle_up_obj)

        self.tfb = mc.textFieldButtonGrp(l='Up Object', bl='Select', cw3=[100, 130, 50], enable=False,
                                         bc=self.set_up_obj)

        button_row = mc.rowColumnLayout(nc=2, p=layout, w=300)
        button = mc.button(label='Orient Transform', p=button_row, c=self.orient_joints, w=150)
        button = mc.button(label='Toggle Axis Display', p=button_row, c=self.toggle_axis, w=150)

        mc.showWindow()

    def toggle_up_obj(self, *args):
        mc.textFieldButtonGrp(self.tfb, enable=self.use_up_object(), edit=True)

    def use_up_object(self):
        return mc.checkBoxGrp(self.cb3, q=True, v1=True)

    def set_up_obj(self, *args):

        sel = mc.ls(sl=True)

        if len(sel) == 1:
            mc.textFieldButtonGrp(self.tfb, e=True, text=sel[0])
        else:
            mc.confirmDialog(m='Please select on up vector object')

    def get_up_obj(self):
        return mc.textFieldButtonGrp(self.tfb, q=True, text=True)

    def toggle_axis(self, *args):

        for s in mc.ls(sl=True):

            if mc.attributeQuery('displayLocalAxis', node=s, exists=True):
                state = mc.getAttr(s + '.displayLocalAxis')

                mc.setAttr(s + '.displayLocalAxis', 1 - state)

    def orient_joints(self, *args):

        axis = [None, 'X', 'Y', 'Z']

        aim_axis = axis[mc.radioButtonGrp(self.rg1, q=True, sl=True)]
        up_axis = axis[mc.radioButtonGrp(self.rg2, q=True, sl=True)]

        inv_aim = mc.checkBoxGrp(self.cb1, q=True, v1=True)
        inv_up = mc.checkBoxGrp(self.cb2, q=True, v1=True)

        selection = mc.ls(selection=True)

        if len(selection) != 2:
            mc.confirmDialog(m='Please select a target and the object to orient.', t='Orient Transforms')
            return

        source = selection[1]
        target = selection[0]

        aim_vec = [0, 0, 0]
        up_vec = [0, 0, 0]

        if aim_axis == 'X':
            aim_vec[0] = 1
        elif aim_axis == 'Y':
            aim_vec[1] = 1
        elif aim_axis == 'Z':
            aim_vec[2] = 1

        if up_axis == 'X':
            up_vec[0] = 1
        elif up_axis == 'Y':
            up_vec[1] = 1
        elif up_axis == 'Z':
            up_vec[2] = 1

        if inv_aim:
            aim_vec[0] *= -1
            aim_vec[1] *= -1
            aim_vec[2] *= -1

        if inv_up:
            up_vec[0] *= -1
            up_vec[1] *= -1
            up_vec[2] *= -1

        child_xform = []= []

        tmp_locs = []
        tmp_cons = []

        at = Transform()

        for child in mc.listRelatives(source, children=True, pa=True):

            if mc.nodeType(child) in ['transform', 'joint']:

                loc = mc.spaceLocator()[0]

                mc.matchTransform(loc, child)

                con = mc.parentConstraint(loc, child)[0]

                tmp_locs.append(loc)
                tmp_cons.append(con)


        loc = mc.spaceLocator(name='temp_loc')

        mc.matchTransform(loc, target)

        if self.use_up_object():
            up_obj = self.get_up_obj()
            aim = mc.aimConstraint(loc, source, aimVector=aim_vec, upVector=up_vec, wut='object', wuo=up_obj)

        else:
            aim = mc.aimConstraint(loc, source, aimVector=aim_vec, upVector=up_vec)

        mc.matchTransform(target, loc)
        mc.delete(loc, aim)
        mc.dgdirty( a=True )
        mc.delete( tmp_cons )
        mc.delete( tmp_locs )

        mc.select(selection)


#######################################################################################################################
#
# Metaryx

class Build( Rig ):

    def __init__(self):
        self.assetsPath = None
        self.rigPath    = None
        self.rigFolder = '_rig'
        self.buildBlocksFile = 'buildBlocks.py'
        self.scriptsPath = os.path.join( self.rigFolder, 'scripts' )
        self.metaLayers = [
            'assetClass',
            'assetType',
            'assetSubtype',
            'assetGroup',
            'assetName',
            'assetVariant',
            'assetReference'
        ]

    def read_asset( self, asset={}, metaLayer='assetName'  ):

        print ('readAsset', self.rigPath)

        print ('\n#######################################################################################################################')
        print ('# ')
        print ('# aniMeta read start\n')

        print ('\naniMeta: read asset ', asset['assetName'], asset['assetVariant'])
        metaAsset = {} 
        metaAsset['asset'] = asset 
        metaAsset['metaLayers'] = {}

        # Add general info to build so we can access the asset info during build time
        # buildList.append( 'AssetInfo')
        # buildDict[ 'AssetInfo' ] = print_asset( asset )

        for layer in self.metaLayers: 

            buildList     = []
            buildDict     = {}
            buildListPost = []
            buildDictPost = {}

            # Get File Path
            pathAssetClass = self.get_path ( asset, layer, type='rig' )

            #print 'pathAssetClass', pathAssetClass
            
            # Get Meta Path
            metaPath = self.get_path ( asset, metaLayer=layer, type='meta' )
            
            #print '\nMetaryx: reading metaPath ', metaPath
            
            # redundant? fassetCassScriptsPath = os.path.join ( pathAssetClass, metaryx.scriptsPath )
            assetClassRigPath = os.path.join ( pathAssetClass,  self.rigFolder,  self.buildBlocksFile )
                
            if os.path.isfile( assetClassRigPath ):
                print ('\n\taniMeta: reading file ', assetClassRigPath, '\n')
                
                lines = []
                
                with open(assetClassRigPath, 'r') as f:
                    lines = f.readlines() 
                
                for line in lines:
                    
                    if '{' and '}' in line: 
                       
                        # Ignore Out-Commented lines
                        if '#{' in line:
                            continue
                            
                        d = ast.literal_eval( line )
                        
                        if type( d ) is dict :

                            buildType = 'default'
                            blockCode = ''

                            if 'buildType' in d:
                                buildType = d['buildType']

                            blockName = d['blockName']
                            
                            #print '\t\taniMeta: reading block ', blockName


                            if buildType == 'default' or buildType == 'post':
                                blockCode += '\n\t####################################################################################\n'
                                blockCode += '\t#\n'
                                blockCode += '\t# ' + metaPath + ' -> ' + blockName + '\n\n'

                            # Get File Path
                            blockCodeFilePath = os.path.join(  pathAssetClass, self.scriptsPath, d['blockFile'] + '.py' )
                            if os.path.isfile( blockCodeFilePath ) :

                                # Read Code Block
                                with open( blockCodeFilePath ) as file_obj:
                                    blockCode += file_obj.read()

                            else:
                                blockCode += "# ERROR: can not open file " +  blockCodeFilePath + "\n"

                            if buildType == 'default' or buildType == 'post':
                                blockCode += '\n\n\t# ' + metaPath + ' -> ' + blockName + '\n'
                                blockCode += '\t#\n'
                                blockCode += '\t####################################################################################\n'

                            if buildType == 'default':
                                buildList.append( blockName )
                                buildDict[blockName] = blockCode

                            if buildType == 'post':
                                buildListPost.append( blockName )
                                buildDictPost[blockName] = blockCode

                            # Replace the keys and the corresponding code in a
                            # given block file using identificators
                            if buildType == 'keyReplace':
                                keywordDict = json.loads(blockCode)
                                layer = d['metaLayer']

                                if layer in metaAsset['metaLayers']:

                                    post = False

                                    code = ''

                                    found =False

                                    # Get the current code
                                    if blockName in  metaAsset['metaLayers'][layer]['buildDict']:
                                        code = metaAsset['metaLayers'][layer]['buildDict'][blockName]
                                        found = True
                                    elif  blockName in  metaAsset['metaLayers'][layer]['buildDictPost']:
                                        code = metaAsset['metaLayers'][layer]['buildDictPost'][blockName]
                                        post = True
                                    else:
                                        mc.confirmDialog( m='Can not find key ' + blockName +  ' in layer ' + layer )

                                    # Replace the code partions, keyword for keyword
                                    for key in keywordDict.keys():

                                        if key in code:
                                            code = code.replace( key, str( keywordDict[key] ) )

                                    # save the new code
                                    if post:
                                        metaAsset['metaLayers'][layer]['buildDictPost'][blockName] = code
                                    else:
                                        metaAsset['metaLayers'][layer]['buildDict'][blockName] = code

                            if buildType == 'blockReplace':

                                layer = d['metaLayer']

                                if layer in metaAsset['metaLayers']:

                                    found = False
                                    post  = False

                                    # Get the current code
                                    if blockName in  metaAsset['metaLayers'][layer]['buildDict']:
                                        found = True
                                    elif  blockName in  metaAsset['metaLayers'][layer]['buildDictPost']:
                                        found = True
                                        post = True
                                    else:
                                        mc.confirmDialog( m='Can not find key ' + blockName +  ' in layer ' + layer )

                                    if found:
                                        # save the new code

                                        code = '\n#blockReplace Start:'+ metaPath + ' -> ' + blockName + '\n\n'
                                        code += blockCode
                                        code += '\n#blockReplace End:'+ metaPath + ' -> ' + blockName + '\n\n'

                                        if post:
                                            metaAsset['metaLayers'][layer]['buildDictPost'][blockName] = code
                                        else:
                                            metaAsset['metaLayers'][layer]['buildDict'][blockName] = code

                        # Reset the Dict to avoid spill-overs
                        d=None

            if len ( buildList ) > 0:
            
                metaBlock = { 'buildList' : buildList, 'buildDict' : buildDict }

                if len( buildListPost ):
                    metaBlock['buildDictPost'] = buildDictPost
                    metaBlock['buildListPost'] = buildListPost

                # Get current dict
                assetLayers = metaAsset['metaLayers']
                
                # Add a new block
                assetLayers[metaPath] = metaBlock 
                 
                # Save in Meta Asset 
                metaAsset['metaLayers'] = assetLayers 
                            
            
            if layer == metaLayer:
                break     

        print ('\n# aniMeta read end')
        print ('# ')
        print ('#######################################################################################################################\n\n')

        return metaAsset

    def rig( self, metaAsset={}, metaLayer='assetVariant', writeFile=False,  executeFile=False, printShell=True, buildByBlock=False, saveFile=True, stopAtBlock=None  ):

        #writeFile = False
        #executeFile = False
        #printShell  = True
        #metaLayer = 'assetClass'
        
        asset = metaAsset['asset']
        code = ''
        metaPath = self.get_path ( asset, metaLayer, type='meta' )

        if not 'metaLayers' in metaAsset:
            mc.warning( 'aniMeta: asset has no metaLayers.')
            return None

        metaPaths = metaAsset['metaLayers'].keys() 
        metaPaths.sort( key=len )
        
        buildFilePath = self.get_path ( asset, metaLayer, type='rig' )

        if not os.path.isdir( buildFilePath ):
            os.makedirs( buildFilePath )

        
        buildFilePath = os.path.join( buildFilePath,  asset['assetName'] + '_' + asset['assetVariant'] +'.py' )

        print ('\n#######################################################################################################################')
        print ('# ')
        print ('# aniMeta build start\n')

        print ('\naniMeta Build')
        print ('\tMeta Layer       ', metaLayer)
        print ('\tAsset Layer      ', asset[metaLayer])
        print ('\tMeta Layer       ', metaLayer)
        print ('\tMeta Path        ', metaPath)
        print ('\tBuild File Path  ', buildFilePath)
        
        code = ''
        code += '####################################################################################\n'
        code += '# Global Asset Info\n'
        code += self.print_asset( asset )
        code += '\n'

        codePost = ''
        codePost += '####################################################################################\n'
        codePost += '# Post Build Code\n'
        codePost += '\n'

        def create_block(  metaPath, buildList, buildDict ):

            stopped = False

            block = '\n'

            block += '####################################################################################\n'
            block += '#\n'
            block += '# ' + metaPath + '\n'
            block += '\n'
            block += '\nprint \'\\nBuild Layer: ' + metaPath + '\'\n'
            block += '\n'

            for item in buildList:
                if buildDict[item] is not None:
                    block += 'print \'\\n' + metaPath + ' --> ' + item + '\''
                    block += buildDict[item]
                    if stopAtBlock:
                        if stopAtBlock == item:
                            block += 'print \'\\nStopping build @ ' + metaPath + ' --> ' + item + '\''
                            stopped = True
                            break

            block += '\n# ' + metaPath + '\n'
            block += '#\n'
            block += '####################################################################################\n\n'

            return block, stopped

        stopped = False

        for i in range ( 0, len ( metaPaths ) ):

            buildList = metaAsset['metaLayers'][metaPaths[i]]['buildList']
            buildDict = metaAsset['metaLayers'][metaPaths[i]]['buildDict']

            block = create_block( metaPaths[i],  buildList, buildDict )
            code +=  block[0]
            stopped = block[1]


            if 'buildListPost' in metaAsset['metaLayers'][metaPaths[i]]:
                buildListPost = metaAsset['metaLayers'][metaPaths[i]]['buildListPost']
                buildDictPost = metaAsset['metaLayers'][metaPaths[i]]['buildDictPost']
                block = create_block( metaPaths[i],  buildListPost, buildDictPost )
                codePost +=  block[0]
                stopped = block[1]

            if stopped:
                break

            if buildByBlock == True:

                with open(buildFilePath, 'w') as file_obj:
                    file_obj.write( block )

                print ('####################################################################################')
                print ('#')
                print ("# Build: ", metaPaths[i] + '\n')
                execfile(  self.buildFilePath )

            if  self.metaLayers[i] ==  metaLayer:
                print ('Stopping at meta layer ', metaLayer)
                break

        code +=  codePost

        if printShell:
            print (code)
            
        if writeFile:
            try:
                with open(buildFilePath, 'w') as file_obj:
                    file_obj.write( block )

                print ('\naniMeta: build file saved to   ',  buildFilePath)
            except:
                print ('aniMeta: there was a problem saving the build file to ',  buildFilePath)
                pass
                
        if executeFile:
            try:
                print ("\nExecuting build file:          ",  buildFilePath)
                execfile(  buildFilePath )
                print ('\naniMeta: build file execution finished.\n')


            except NameError as e:
                print ('\naniMeta: there was a problem executing the build file ')
                print (e)
                locals()[e.message.split("'")[1]] = 0
                pass 
        if saveFile == True:
            path = os.path.join(  self.get_path( asset, 'assetVariant', type='asset'  ), 'Rig'  )
            filePath = os.path.join(  path, asset['assetName'] + '_' + asset['assetVariant'] + '.ma'  )

            try:
                os.makedirs( path,  True )
            except:
                pass

            # TEMP!
            try:
                mc.delete( mc.ls( typ='unknown') )
            except: pass

            mc.file( rename=filePath )
            mc.file( save=True, force=True, type="mayaAscii" )
            mm.eval(  'addRecentFile(" ' + filePath.replace(os.sep, '/') + '", "mayaAscii") ')
            print ('aniMeta: built asset saved to  ', filePath)

        print ('\n# aniMeta build end')
        print ('# ')
        print ('#######################################################################################################################\n\n')


    def get_path( self, asset, metaLayer='', type='asset' ) :
        path = None
        #print metaryx.__file__
        #print 'metaryx.assetsPath', self.assetsPath
        #print 'metaryx.rigPath   ', self.rigPath

        if type == 'asset':
            path = self.assetsPath
        if type == 'rig':
            path = self.rigPath
        if type == 'meta':
            path = ''
        for layer in self.metaLayers:
            if layer in asset:
                
                if type == 'rig' or type == 'asset':
                    path = os.path.join( path, asset[layer] )
                    
                if type == 'meta':
                    path += '|' + asset[layer]  
                    
                if layer == metaLayer:
                    break
            else:
                break  
        return path         


    def get_asset_path( self, assetDict, asset=False ):

        if self.rigPath is None:
            mc.warning('aniMeta.Build: rigPath is not specified.')
            return None

        model_path = self.rigPath

        # Get Geo or other non-rigging dats
        if asset:
            model_path = self.assetsPath

        for layer in self.metaLayers:

            if layer in assetDict:
                if layer != 'assetReference':
                    #model_path = os.path.join( model_path, assetDict[layer] )
                    model_path += '/' + assetDict[layer]

        return model_path


    def import_file( self, filePath, newParent='', suffix="mayaAscii" ):
        importGroup = 'import_temp'

        if os.path.isfile( filePath ):

            mc.file(filePath, i=True, type=suffix, rnn=True, ignoreVersion=True, options="mo=0", loadReferenceDepth="all",
                    gr=True, gn=importGroup)
            geos = mc.listRelatives(importGroup, c=True, pa=True)

            if newParent is None:
                mc.parent( geos, world=True )
                mc.delete(importGroup)
            elif mc.objExists(newParent):
                mc.parent(geos, newParent)
                mc.delete(importGroup)
            else:
                grp = mc.createNode( 'transform', name=self.short_name( newParent ))
                mc.parent(geos, grp)
                mc.delete(importGroup)

            mc.select(cl=True)
            return geos
        else:
            mc.warning( 'aniMeta: File does not exist ', filePath )
            return None

    def print_asset( self, assetDict):
        out = "\n# Asset Dict\n"
        out = "ASSET = {}\n"

        out += "ASSET['assetClass']     = '" + assetDict['assetClass'] + "'\n"
        out += "ASSET['assetType']      = '" + assetDict['assetType'] + "'\n"
        out += "ASSET['assetSubtype']   = '" + assetDict['assetSubtype'] + "'\n"
        out += "ASSET['assetGroup']     = '" + assetDict['assetGroup'] + "'\n"
        out += "ASSET['assetName']      = '" + assetDict['assetName'] + "'\n"
        out += "ASSET['assetVariant']   = '" + assetDict['assetVariant'] + "'\n"
        if 'assetReference' in assetDict:
            out += "ASSET['assetReference'] = '" + assetDict['assetReference'] + "'\n"
        return out