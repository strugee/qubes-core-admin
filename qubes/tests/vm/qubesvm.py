# pylint: disable=protected-access

#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2014-2015  Joanna Rutkowska <joanna@invisiblethingslab.com>
# Copyright (C) 2014-2015  Wojtek Porczyk <woju@invisiblethingslab.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, see <https://www.gnu.org/licenses/>.
#
import base64
import os

import unittest
import uuid
import datetime
import lxml.etree
import unittest.mock

import shutil

import qubes
import qubes.exc
import qubes.config
import qubes.vm
import qubes.vm.qubesvm

import qubes.tests
import qubes.tests.vm

class TestApp(object):
    labels = {1: qubes.Label(1, '0xcc0000', 'red')}

    def __init__(self):
        self.domains = {}

class TestProp(object):
    # pylint: disable=too-few-public-methods
    __name__ = 'testprop'

class TestDeviceCollection(object):
    def __init__(self):
        self._list = []

    def persistent(self):
        return self._list

class TestQubesDB(object):
    def __init__(self):
        self.data = {}

    def write(self, path, value):
        self.data[path] = value

    def rm(self, path):
        if path.endswith('/'):
            for key in [x for x in self.data if x.startswith(path)]:
                del self.data[key]
        else:
            self.data.pop(path, None)

class TestVM(object):
    # pylint: disable=too-few-public-methods
    app = TestApp()

    def __init__(self, **kwargs):
        self.running = False
        self.installed_by_rpm = False
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.devices = {'pci': TestDeviceCollection()}

    def is_running(self):
        return self.running


class TC_00_setters(qubes.tests.QubesTestCase):
    def setUp(self):
        super().setUp()
        self.vm = TestVM()
        self.prop = TestProp()


    def test_000_setter_qid(self):
        self.assertEqual(
            qubes.vm._setter_qid(self.vm, self.prop, 5), 5)

    def test_001_setter_qid_lt_0(self):
        with self.assertRaises(ValueError):
            qubes.vm._setter_qid(self.vm, self.prop, -1)

    def test_002_setter_qid_gt_max(self):
        with self.assertRaises(ValueError):
            qubes.vm._setter_qid(self.vm,
                self.prop, qubes.config.max_qid + 5)

    @unittest.skip('test not implemented')
    def test_020_setter_kernel(self):
        pass


    def test_030_setter_label_object(self):
        label = TestApp.labels[1]
        self.assertIs(label,
            qubes.vm.setter_label(self.vm, self.prop, label))

    def test_031_setter_label_getitem(self):
        label = TestApp.labels[1]
        self.assertIs(label,
            qubes.vm.setter_label(self.vm, self.prop, 'label-1'))

    # there is no check for self.app.get_label()

    def test_040_setter_virt_mode(self):
        self.assertEqual(
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'hvm'),
            'hvm')
        self.assertEqual(
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'HVM'),
            'hvm')
        self.assertEqual(
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'PV'),
            'pv')
        self.assertEqual(
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'pvh'),
            'pvh')
        self.vm.devices['pci']._list.append(object())
        with self.assertRaises(ValueError):
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'pvh')
        with self.assertRaises(ValueError):
            qubes.vm.qubesvm._setter_virt_mode(self.vm, self.prop, 'True')

class TC_10_default(qubes.tests.QubesTestCase):
    def setUp(self):
        super().setUp()
        self.app = TestApp()
        self.vm = TestVM(app=self.app)
        self.prop = TestProp()

    def test_000_default_with_template_simple(self):
        default_getter = qubes.vm.qubesvm._default_with_template('kernel',
            'dfl-kernel')
        self.assertEqual(default_getter(self.vm), 'dfl-kernel')
        self.vm.template = None
        self.assertEqual(default_getter(self.vm), 'dfl-kernel')
        self.vm.template = unittest.mock.Mock()
        self.vm.template.kernel = 'template-kernel'
        self.assertEqual(default_getter(self.vm), 'template-kernel')

    def test_001_default_with_template_callable(self):
        default_getter = qubes.vm.qubesvm._default_with_template('kernel',
            lambda x: x.app.default_kernel)
        self.app.default_kernel = 'global-dfl-kernel'
        self.assertEqual(default_getter(self.vm), 'global-dfl-kernel')
        self.vm.template = None
        self.assertEqual(default_getter(self.vm), 'global-dfl-kernel')
        self.vm.template = unittest.mock.Mock()
        self.vm.template.kernel = 'template-kernel'
        self.assertEqual(default_getter(self.vm), 'template-kernel')

    def test_010_default_virt_mode(self):
        default_getter = qubes.vm.qubesvm._default_with_template('kernel',
            lambda x: x.app.default_kernel)
        self.assertEqual(qubes.vm.qubesvm._default_virt_mode(self.vm),
            'pvh')
        self.vm.template = unittest.mock.Mock()
        self.vm.template.virt_mode = 'hvm'
        self.assertEqual(qubes.vm.qubesvm._default_virt_mode(self.vm),
            'hvm')
        self.vm.template = None
        self.assertEqual(qubes.vm.qubesvm._default_virt_mode(self.vm),
            'pvh')
        self.vm.devices['pci'].persistent().append('some-dev')
        self.assertEqual(qubes.vm.qubesvm._default_virt_mode(self.vm),
            'hvm')


class QubesVMTestsMixin(object):
    property_no_default = object()

    def setUp(self):
        super(QubesVMTestsMixin, self).setUp()
        self.app = qubes.tests.vm.TestApp()
        self.app.vmm.offline_mode = True
        self.app.default_kernel = None
        # when full test run is called, extensions are loaded by earlier
        # tests, but if just this test class is run, load them manually here,
        # to have the same behaviour
        qubes.ext.get_extensions()

    def tearDown(self):
        try:
            self.app.domains.close()
        except AttributeError:
            pass
        super(QubesVMTestsMixin, self).tearDown()

    def get_vm(self, name='test', cls=qubes.vm.qubesvm.QubesVM, **kwargs):
        vm = cls(self.app, None,
            qid=kwargs.pop('qid', 1), name=qubes.tests.VMPREFIX + name,
            **kwargs)
        self.app.domains[vm.qid] = vm
        self.app.domains[vm.uuid] = vm
        self.app.domains[vm.name] = vm
        self.app.domains[vm] = vm
        self.addCleanup(vm.close)
        return vm

    def assertPropertyValue(self, vm, prop_name, set_value, expected_value,
            expected_xml_content=None):
        # FIXME: any better exception list? or maybe all of that should be a
        # single exception?
        with self.assertNotRaises((ValueError, TypeError, KeyError)):
            setattr(vm, prop_name, set_value)
        self.assertEqual(getattr(vm, prop_name), expected_value)
        if expected_xml_content is not None:
            xml = vm.__xml__()
            prop_xml = xml.xpath(
                './properties/property[@name=\'{}\']'.format(prop_name))
            self.assertEqual(len(prop_xml), 1, "Property not found in XML")
            self.assertEqual(prop_xml[0].text, expected_xml_content)

    def assertPropertyInvalidValue(self, vm, prop_name, set_value):
        orig_value_set = True
        orig_value = None
        try:
            orig_value = getattr(vm, prop_name)
        except AttributeError:
            orig_value_set = False
        # FIXME: any better exception list? or maybe all of that should be a
        # single exception?
        with self.assertRaises((ValueError, TypeError, KeyError)):
            setattr(vm, prop_name, set_value)
        if orig_value_set:
            self.assertEqual(getattr(vm, prop_name), orig_value)
        else:
            with self.assertRaises(AttributeError):
                getattr(vm, prop_name)

    def assertPropertyDefaultValue(self, vm, prop_name,
            expected_default=property_no_default):
        if expected_default is self.property_no_default:
            with self.assertRaises(AttributeError):
                getattr(vm, prop_name)
        else:
            with self.assertNotRaises(AttributeError):
                self.assertEqual(getattr(vm, prop_name), expected_default)
        xml = vm.__xml__()
        prop_xml = xml.xpath(
            './properties/property[@name=\'{}\']'.format(prop_name))
        self.assertEqual(len(prop_xml), 0, "Property still found in XML")

    def _test_generic_bool_property(self, vm, prop_name, default=False):
        self.assertPropertyDefaultValue(vm, prop_name, default)
        self.assertPropertyValue(vm, prop_name, False, False, 'False')
        self.assertPropertyValue(vm, prop_name, True, True, 'True')
        delattr(vm, prop_name)
        self.assertPropertyDefaultValue(vm, prop_name, default)
        self.assertPropertyValue(vm, prop_name, 'True', True, 'True')
        self.assertPropertyValue(vm, prop_name, 'False', False, 'False')
        self.assertPropertyInvalidValue(vm, prop_name, 'xxx')
        self.assertPropertyValue(vm, prop_name, 123, True)
        self.assertPropertyInvalidValue(vm, prop_name, '')


class TC_90_QubesVM(QubesVMTestsMixin, qubes.tests.QubesTestCase):
    def test_000_init(self):
        self.get_vm()

    def test_001_init_no_qid_or_name(self):
        with self.assertRaises(AssertionError):
            qubes.vm.qubesvm.QubesVM(self.app, None,
                name=qubes.tests.VMPREFIX + 'test')
        with self.assertRaises(AssertionError):
            qubes.vm.qubesvm.QubesVM(self.app, None,
                qid=1)

    def test_003_init_fire_domain_init(self):
        class TestVM2(qubes.vm.qubesvm.QubesVM):
            event_fired = False
            @qubes.events.handler('domain-init')
            def on_domain_init(self, event): # pylint: disable=unused-argument
                self.__class__.event_fired = True

        TestVM2(self.app, None, qid=1, name=qubes.tests.VMPREFIX + 'test')
        self.assertTrue(TestVM2.event_fired)

    def test_004_uuid_autogen(self):
        vm = self.get_vm()
        self.assertTrue(hasattr(vm, 'uuid'))

    def test_100_qid(self):
        vm = self.get_vm()
        self.assertIsInstance(vm.qid, int)
        with self.assertRaises(AttributeError):
            vm.qid = 2

    def test_110_name(self):
        vm = self.get_vm()
        self.assertIsInstance(vm.name, str)

    def test_120_uuid(self):
        my_uuid = uuid.uuid4()
        vm = self.get_vm(uuid=my_uuid)
        self.assertIsInstance(vm.uuid, uuid.UUID)
        self.assertIs(vm.uuid, my_uuid)
        with self.assertRaises(AttributeError):
            vm.uuid = uuid.uuid4()

    @unittest.skip('TODO: how to not fail on making an icon symlink here?')
    def test_130_label(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'label')
        self.assertPropertyValue(vm, 'label', self.app.labels[1],
            self.app.labels[1], 'label-1')
        del vm.label
        self.assertPropertyDefaultValue(vm, 'label')
        self.assertPropertyValue(vm, 'label', 'red',
            self.app.labels[1], 'label-1')
        self.assertPropertyValue(vm, 'label', 'label-1',
            self.app.labels[1], 'label-1')

    def test_131_label_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'label', 'invalid')
        self.assertPropertyInvalidValue(vm, 'label', 123)

    def test_160_memory(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'memory', 400)
        self.assertPropertyValue(vm, 'memory', 500, 500, '500')
        del vm.memory
        self.assertPropertyDefaultValue(vm, 'memory', 400)
        self.assertPropertyValue(vm, 'memory', '500', 500, '500')

    def test_161_memory_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'memory', -100)
        self.assertPropertyInvalidValue(vm, 'memory', '-100')
        self.assertPropertyInvalidValue(vm, 'memory', '')
        # TODO: higher than maxmem
        # TODO: human readable setter (500M, 4G)?

    def test_170_maxmem(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'maxmem',
            self.app.host.memory_total / 1024 / 2)
        self.assertPropertyValue(vm, 'maxmem', 500, 500, '500')
        del vm.maxmem
        self.assertPropertyDefaultValue(vm, 'maxmem',
            self.app.host.memory_total / 1024 / 2)
        self.assertPropertyValue(vm, 'maxmem', '500', 500, '500')

    def test_171_maxmem_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'maxmem', -100)
        self.assertPropertyInvalidValue(vm, 'maxmem', '-100')
        self.assertPropertyInvalidValue(vm, 'maxmem', '')
        # TODO: lower than memory
        # TODO: human readable setter (500M, 4G)?

    def test_190_vcpus(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'vcpus', 2)
        self.assertPropertyValue(vm, 'vcpus', 3, 3, '3')
        del vm.vcpus
        self.assertPropertyDefaultValue(vm, 'vcpus', 2)
        self.assertPropertyValue(vm, 'vcpus', '3', 3, '3')

    def test_191_vcpus_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'vcpus', 0)
        self.assertPropertyInvalidValue(vm, 'vcpus', -2)
        self.assertPropertyInvalidValue(vm, 'vcpus', '-2')
        self.assertPropertyInvalidValue(vm, 'vcpus', '')

    def test_200_debug(self):
        vm = self.get_vm()
        self._test_generic_bool_property(vm, 'debug', False)

    def test_210_installed_by_rpm(self):
        vm = self.get_vm()
        self._test_generic_bool_property(vm, 'installed_by_rpm', False)

    def test_220_include_in_backups(self):
        vm = self.get_vm()
        self._test_generic_bool_property(vm, 'include_in_backups', True)

    @qubes.tests.skipUnlessDom0
    def test_250_kernel(self):
        kernels = os.listdir(os.path.join(
            qubes.config.qubes_base_dir,
            qubes.config.system_path['qubes_kernels_base_dir']))
        if not len(kernels):
            self.skipTest('Needs at least one kernel installed')
        self.app.default_kernel = kernels[0]
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'kernel', kernels[0])
        self.assertPropertyValue(vm, 'kernel', kernels[-1], kernels[-1],
            kernels[-1])
        del vm.kernel
        self.assertPropertyDefaultValue(vm, 'kernel', kernels[0])

    @qubes.tests.skipUnlessDom0
    def test_251_kernel_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'kernel', 123)
        self.assertPropertyInvalidValue(vm, 'kernel', 'invalid')

    def test_252_kernel_empty(self):
        vm = self.get_vm()
        self.assertPropertyValue(vm, 'kernel', '', '', '')
        self.assertPropertyValue(vm, 'kernel', None, '', '')

    def test_260_kernelopts(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'kernelopts',
            qubes.config.defaults['kernelopts'])
        self.assertPropertyValue(vm, 'kernelopts', 'some options',
            'some options', 'some options')
        del vm.kernelopts
        self.assertPropertyDefaultValue(vm, 'kernelopts',
            qubes.config.defaults['kernelopts'])
        self.assertPropertyValue(vm, 'kernelopts', '',
            '', '')
        # TODO?
        # self.assertPropertyInvalidValue(vm, 'kernelopts', None),

    @unittest.skip('test not implemented')
    def test_261_kernelopts_pcidevs(self):
        vm = self.get_vm()
        # how to do that here? use dummy DeviceManager/DeviceCollection?
        # Disable events?
        vm.devices['pci'].attach('something')
        self.assertPropertyDefaultValue(vm, 'kernelopts',
            qubes.config.defaults['kernelopts_pcidevs'])

    def test_270_qrexec_timeout(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'qrexec_timeout', 60)
        self.assertPropertyValue(vm, 'qrexec_timeout', 3, 3, '3')
        del vm.qrexec_timeout
        self.assertPropertyDefaultValue(vm, 'qrexec_timeout', 60)
        self.assertPropertyValue(vm, 'qrexec_timeout', '3', 3, '3')

    def test_271_qrexec_timeout_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'qrexec_timeout', -2)
        self.assertPropertyInvalidValue(vm, 'qrexec_timeout', '-2')
        self.assertPropertyInvalidValue(vm, 'qrexec_timeout', '')

    def test_272_qrexec_timeout_global_changed(self):
        self.app.default_qrexec_timeout = 123
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'qrexec_timeout', 123)
        self.assertPropertyValue(vm, 'qrexec_timeout', 3, 3, '3')
        del vm.qrexec_timeout
        self.assertPropertyDefaultValue(vm, 'qrexec_timeout', 123)
        self.assertPropertyValue(vm, 'qrexec_timeout', '3', 3, '3')

    def test_280_autostart(self):
        vm = self.get_vm()
        # FIXME any better idea to not involve systemctl call at this stage?
        vm.events_enabled = False
        self._test_generic_bool_property(vm, 'autostart', False)

    @qubes.tests.skipUnlessDom0
    def test_281_autostart_systemd(self):
        vm = self.get_vm()
        self.assertFalse(os.path.exists(
            '/etc/systemd/system/multi-user.target.wants/'
            'qubes-vm@{}.service'.format(vm.name)),
            "systemd service enabled before setting autostart")
        vm.autostart = True
        self.assertTrue(os.path.exists(
            '/etc/systemd/system/multi-user.target.wants/'
            'qubes-vm@{}.service'.format(vm.name)),
            "systemd service not enabled by autostart=True")
        vm.autostart = False
        self.assertFalse(os.path.exists(
            '/etc/systemd/system/multi-user.target.wants/'
            'qubes-vm@{}.service'.format(vm.name)),
            "systemd service not disabled by autostart=False")
        vm.autostart = True
        del vm.autostart
        self.assertFalse(os.path.exists(
            '/etc/systemd/system/multi-user.target.wants/'
            'qubes-vm@{}.service'.format(vm.name)),
            "systemd service not disabled by resetting autostart")

    def test_290_management_dispvm(self):
        vm = self.get_vm()
        vm2 = self.get_vm('test2', qid=2)
        self.app.management_dispvm = None
        self.assertPropertyDefaultValue(vm, 'management_dispvm', None)
        self.app.management_dispvm = vm
        try:
            self.assertPropertyDefaultValue(vm, 'management_dispvm', vm)
            self.assertPropertyValue(vm, 'management_dispvm',
                'test-inst-test2', vm2)
        finally:
            self.app.management_dispvm = None

    def test_291_management_dispvm_template_based(self):
        tpl = self.get_vm(name='tpl', cls=qubes.vm.templatevm.TemplateVM)
        vm = self.get_vm(cls=qubes.vm.appvm.AppVM, template=tpl, qid=2)
        vm2 = self.get_vm('test2', qid=3)
        del vm.volumes
        self.app.management_dispvm = None
        try:
            self.assertPropertyDefaultValue(vm, 'management_dispvm', None)
            self.app.management_dispvm = vm
            self.assertPropertyDefaultValue(vm, 'management_dispvm', vm)
            tpl.management_dispvm = vm2
            self.assertPropertyDefaultValue(vm, 'management_dispvm', vm2)
            self.assertPropertyValue(vm, 'management_dispvm',
                'test-inst-test2', vm2)
        finally:
            self.app.management_dispvm = None

    @unittest.skip('TODO')
    def test_320_seamless_gui_mode(self):
        vm = self.get_vm()
        self._test_generic_bool_property(vm, 'seamless_gui_mode')
        # TODO: reject setting to True when guiagent_installed is false

    def test_330_mac(self):
        vm = self.get_vm()
        # TODO: calculate proper default here
        default_mac = vm.mac
        self.assertIsNotNone(default_mac)
        self.assertPropertyDefaultValue(vm, 'mac', default_mac)
        self.assertPropertyValue(vm, 'mac', '00:11:22:33:44:55',
            '00:11:22:33:44:55', '00:11:22:33:44:55')
        del vm.mac
        self.assertPropertyDefaultValue(vm, 'mac', default_mac)

    def test_331_mac_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'mac', 123)
        self.assertPropertyInvalidValue(vm, 'mac', 'invalid')
        self.assertPropertyInvalidValue(vm, 'mac', '00:11:22:33:44:55:66')

    def test_340_default_user(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'default_user', 'user')
        self.assertPropertyValue(vm, 'default_user', 'someuser', 'someuser',
            'someuser')
        del vm.default_user
        self.assertPropertyDefaultValue(vm, 'default_user', 'user')
        self.assertPropertyValue(vm, 'default_user', 123, '123', '123')
        vm.default_user = 'user'
        # TODO: check propagation for template-based VMs

    @unittest.skip('TODO')
    def test_350_timezone(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'timezone', 'localtime')
        self.assertPropertyValue(vm, 'timezone', 0, 0, '0')
        del vm.timezone
        self.assertPropertyDefaultValue(vm, 'timezone', 'localtime')
        self.assertPropertyValue(vm, 'timezone', '0', 0, '0')
        self.assertPropertyValue(vm, 'timezone', -3600, -3600, '-3600')
        self.assertPropertyValue(vm, 'timezone', 7200, 7200, '7200')

    @unittest.skip('TODO')
    def test_350_timezone_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'timezone', 'xxx')

    @unittest.skip('TODO')
    def test_360_drive(self):
        vm = self.get_vm()
        self.assertPropertyDefaultValue(vm, 'drive', None)
        # self.execute_tests('drive', [
        #     ('hd:dom0:/tmp/drive.img', 'hd:dom0:/tmp/drive.img', True),
        #     ('hd:/tmp/drive.img', 'hd:dom0:/tmp/drive.img', True),
        #     ('cdrom:dom0:/tmp/drive.img', 'cdrom:dom0:/tmp/drive.img', True),
        #     ('cdrom:/tmp/drive.img', 'cdrom:dom0:/tmp/drive.img', True),
        #     ('/tmp/drive.img', 'cdrom:dom0:/tmp/drive.img', True),
        #     ('hd:drive.img', '', False),
        #     ('drive.img', '', False),
        # ])

    def test_400_backup_timestamp(self):
        vm = self.get_vm()
        timestamp = datetime.datetime(2016, 1, 1, 12, 14, 2)
        timestamp_str = timestamp.strftime('%s')
        self.assertPropertyDefaultValue(vm, 'backup_timestamp', None)
        self.assertPropertyValue(vm, 'backup_timestamp', int(timestamp_str),
            int(timestamp_str), timestamp_str)
        del vm.backup_timestamp
        self.assertPropertyDefaultValue(vm, 'backup_timestamp', None)
        self.assertPropertyValue(vm, 'backup_timestamp', timestamp_str,
            int(timestamp_str))

    def test_401_backup_timestamp_invalid(self):
        vm = self.get_vm()
        self.assertPropertyInvalidValue(vm, 'backup_timestamp', 'xxx')
        self.assertPropertyInvalidValue(vm, 'backup_timestamp', None)

    def test_500_property_migrate_virt_mode(self):
        xml_template = '''
        <domain class="QubesVM" id="domain-1">
            <properties>
                <property name="qid">1</property>
                <property name="name">testvm</property>
                <property name="label" ref="label-1" />
                <property name="hvm">{hvm_value}</property>
            </properties>
        </domain>
        '''
        xml = lxml.etree.XML(xml_template.format(hvm_value='True'))
        vm = qubes.vm.qubesvm.QubesVM(self.app, xml)
        self.assertEqual(vm.virt_mode, 'hvm')
        with self.assertRaises(AttributeError):
            vm.hvm

        xml = lxml.etree.XML(xml_template.format(hvm_value='False'))
        vm = qubes.vm.qubesvm.QubesVM(self.app, xml)
        self.assertEqual(vm.virt_mode, 'pv')
        with self.assertRaises(AttributeError):
            vm.hvm

    def test_600_libvirt_xml_pv(self):
        expected = '''<domain type="xen">
        <name>test-inst-test</name>
        <uuid>7db78950-c467-4863-94d1-af59806384ea</uuid>
        <memory unit="MiB">500</memory>
        <currentMemory unit="MiB">400</currentMemory>
        <vcpu placement="static">2</vcpu>
        <os>
            <type arch="x86_64" machine="xenpv">linux</type>
            <kernel>/tmp/kernel/vmlinuz</kernel>
            <initrd>/tmp/kernel/initramfs</initrd>
            <cmdline>root=/dev/mapper/dmroot ro nomodeset console=hvc0 rd_NO_PLYMOUTH rd.plymouth.enable=0 plymouth.enable=0 nopat</cmdline>
        </os>
        <features>
        </features>
        <clock offset='utc' adjustment='reset'>
            <timer name="tsc" mode="native"/>
        </clock>
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>destroy</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <disk type="block" device="disk">
                <driver name="phy" />
                <source dev="/tmp/kernel/modules.img" />
                <target dev="xvdd" />
                <backenddomain name="dom0" />
            </disk>
            <console type="pty">
                <target type="xen" port="0"/>
            </console>
        </devices>
        </domain>
        '''
        my_uuid = '7db78950-c467-4863-94d1-af59806384ea'
        vm = self.get_vm(uuid=my_uuid)
        vm.netvm = None
        vm.virt_mode = 'pv'
        with unittest.mock.patch('qubes.config.qubes_base_dir',
                '/tmp/qubes-test'):
            kernel_dir = '/tmp/qubes-test/vm-kernels/dummy'
            os.makedirs(kernel_dir, exist_ok=True)
            open(os.path.join(kernel_dir, 'vmlinuz'), 'w').close()
            open(os.path.join(kernel_dir, 'initramfs'), 'w').close()
            self.addCleanup(shutil.rmtree, '/tmp/qubes-test')
            vm.kernel = 'dummy'
        # tests for storage are later
        vm.volumes['kernel'] = unittest.mock.Mock(**{
            'kernels_dir': '/tmp/kernel',
            'block_device.return_value.domain': 'dom0',
            'block_device.return_value.script': None,
            'block_device.return_value.path': '/tmp/kernel/modules.img',
            'block_device.return_value.devtype': 'disk',
            'block_device.return_value.name': 'kernel',
        })
        libvirt_xml = vm.create_config_file()
        self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
            lxml.etree.XML(expected))

    def test_600_libvirt_xml_hvm(self):
        expected = '''<domain type="xen">
        <name>test-inst-test</name>
        <uuid>7db78950-c467-4863-94d1-af59806384ea</uuid>
        <memory unit="MiB">500</memory>
        <currentMemory unit="MiB">400</currentMemory>
        <vcpu placement="static">2</vcpu>
        <cpu mode='host-passthrough'>
            <!-- disable nested HVM -->
            <feature name='vmx' policy='disable'/>
            <feature name='svm' policy='disable'/>
            <!-- disable SMAP inside VM, because of Linux bug -->
            <feature name='smap' policy='disable'/>
        </cpu>
        <os>
            <type arch="x86_64" machine="xenfv">hvm</type>
                <!--
                     For the libxl backend libvirt switches between OVMF (UEFI)
                     and SeaBIOS based on the loader type. This has nothing to
                     do with the hvmloader binary.
                -->
            <loader type="rom">hvmloader</loader>
            <boot dev="cdrom" />
            <boot dev="hd" />
        </os>
        <features>
            <pae/>
            <acpi/>
            <apic/>
            <viridian/>
        </features>
        <clock offset="variable" adjustment="0" basis="localtime" />
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>destroy</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <!-- server_ip is the address of stubdomain. It hosts it's own DNS server. -->
            <emulator type="stubdom-linux" />
            <input type="tablet" bus="usb"/>
            <video>
                <model type="vga"/>
            </video>
            <graphics type="qubes"/>
        </devices>
        </domain>
        '''
        my_uuid = '7db78950-c467-4863-94d1-af59806384ea'
        vm = self.get_vm(uuid=my_uuid)
        vm.netvm = None
        vm.virt_mode = 'hvm'
        libvirt_xml = vm.create_config_file()
        self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
            lxml.etree.XML(expected))

    def test_600_libvirt_xml_hvm_dom0_kernel(self):
        expected = '''<domain type="xen">
        <name>test-inst-test</name>
        <uuid>7db78950-c467-4863-94d1-af59806384ea</uuid>
        <memory unit="MiB">500</memory>
        <currentMemory unit="MiB">400</currentMemory>
        <vcpu placement="static">2</vcpu>
        <cpu mode='host-passthrough'>
            <!-- disable nested HVM -->
            <feature name='vmx' policy='disable'/>
            <feature name='svm' policy='disable'/>
            <!-- disable SMAP inside VM, because of Linux bug -->
            <feature name='smap' policy='disable'/>
        </cpu>
        <os>
            <type arch="x86_64" machine="xenfv">hvm</type>
                <!--
                     For the libxl backend libvirt switches between OVMF (UEFI)
                     and SeaBIOS based on the loader type. This has nothing to
                     do with the hvmloader binary.
                -->
            <loader type="rom">hvmloader</loader>
            <boot dev="cdrom" />
            <boot dev="hd" />
            <cmdline>root=/dev/mapper/dmroot ro nomodeset console=hvc0 rd_NO_PLYMOUTH rd.plymouth.enable=0 plymouth.enable=0 nopat</cmdline>
        </os>
        <features>
            <pae/>
            <acpi/>
            <apic/>
            <viridian/>
        </features>
        <clock offset="variable" adjustment="0" basis="localtime" />
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>destroy</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <!-- server_ip is the address of stubdomain. It hosts it's own DNS server. -->
            <emulator type="stubdom-linux" />
            <input type="tablet" bus="usb"/>
            <video>
                <model type="vga"/>
            </video>
            <graphics type="qubes"/>
        </devices>
        </domain>
        '''
        my_uuid = '7db78950-c467-4863-94d1-af59806384ea'
        vm = self.get_vm(uuid=my_uuid)
        vm.netvm = None
        vm.virt_mode = 'hvm'
        with unittest.mock.patch('qubes.config.qubes_base_dir',
                '/tmp/qubes-test'):
            kernel_dir = '/tmp/qubes-test/vm-kernels/dummy'
            os.makedirs(kernel_dir, exist_ok=True)
            open(os.path.join(kernel_dir, 'vmlinuz'), 'w').close()
            open(os.path.join(kernel_dir, 'initramfs'), 'w').close()
            self.addCleanup(shutil.rmtree, '/tmp/qubes-test')
            vm.kernel = 'dummy'
        libvirt_xml = vm.create_config_file()
        self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
            lxml.etree.XML(expected))

    def test_600_libvirt_xml_pvh(self):
        expected = '''<domain type="xen">
        <name>test-inst-test</name>
        <uuid>7db78950-c467-4863-94d1-af59806384ea</uuid>
        <memory unit="MiB">500</memory>
        <currentMemory unit="MiB">400</currentMemory>
        <vcpu placement="static">2</vcpu>
        <cpu mode='host-passthrough'>
            <!-- disable nested HVM -->
            <feature name='vmx' policy='disable'/>
            <feature name='svm' policy='disable'/>
            <!-- disable SMAP inside VM, because of Linux bug -->
            <feature name='smap' policy='disable'/>
        </cpu>
        <os>
            <type arch="x86_64" machine="xenfv">pvh</type>
            <kernel>/tmp/kernel/vmlinuz</kernel>
            <initrd>/tmp/kernel/initramfs</initrd>
            <cmdline>root=/dev/mapper/dmroot ro nomodeset console=hvc0 rd_NO_PLYMOUTH rd.plymouth.enable=0 plymouth.enable=0 nopat</cmdline>
        </os>
        <features>
            <pae/>
            <acpi/>
            <apic/>
            <viridian/>
        </features>
        <clock offset='utc' adjustment='reset'>
            <timer name="tsc" mode="native"/>
        </clock>
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>destroy</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <disk type="block" device="disk">
                <driver name="phy" />
                <source dev="/tmp/kernel/modules.img" />
                <target dev="xvdd" />
                <backenddomain name="dom0" />
            </disk>
            <console type="pty">
                <target type="xen" port="0"/>
            </console>
        </devices>
        </domain>
        '''
        my_uuid = '7db78950-c467-4863-94d1-af59806384ea'
        vm = self.get_vm(uuid=my_uuid)
        vm.netvm = None
        vm.virt_mode = 'pvh'
        with unittest.mock.patch('qubes.config.qubes_base_dir',
                '/tmp/qubes-test'):
            kernel_dir = '/tmp/qubes-test/vm-kernels/dummy'
            os.makedirs(kernel_dir, exist_ok=True)
            open(os.path.join(kernel_dir, 'vmlinuz'), 'w').close()
            open(os.path.join(kernel_dir, 'initramfs'), 'w').close()
            self.addCleanup(shutil.rmtree, '/tmp/qubes-test')
            vm.kernel = 'dummy'
        # tests for storage are later
        vm.volumes['kernel'] = unittest.mock.Mock(**{
            'kernels_dir': '/tmp/kernel',
            'block_device.return_value.domain': 'dom0',
            'block_device.return_value.script': None,
            'block_device.return_value.path': '/tmp/kernel/modules.img',
            'block_device.return_value.devtype': 'disk',
            'block_device.return_value.name': 'kernel',
        })
        libvirt_xml = vm.create_config_file()
        self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
            lxml.etree.XML(expected))

    def test_610_libvirt_xml_network(self):
        expected = '''<domain type="xen">
        <name>test-inst-test</name>
        <uuid>7db78950-c467-4863-94d1-af59806384ea</uuid>
        <memory unit="MiB">500</memory>
        <currentMemory unit="MiB">400</currentMemory>
        <vcpu placement="static">2</vcpu>
        <cpu mode='host-passthrough'>
            <!-- disable nested HVM -->
            <feature name='vmx' policy='disable'/>
            <feature name='svm' policy='disable'/>
            <!-- disable SMAP inside VM, because of Linux bug -->
            <feature name='smap' policy='disable'/>
        </cpu>
        <os>
            <type arch="x86_64" machine="xenfv">hvm</type>
                <!--
                     For the libxl backend libvirt switches between OVMF (UEFI)
                     and SeaBIOS based on the loader type. This has nothing to
                     do with the hvmloader binary.
                -->
            <loader type="rom">hvmloader</loader>
            <boot dev="cdrom" />
            <boot dev="hd" />
        </os>
        <features>
            <pae/>
            <acpi/>
            <apic/>
            <viridian/>
        </features>
        <clock offset="variable" adjustment="0" basis="localtime" />
        <on_poweroff>destroy</on_poweroff>
        <on_reboot>destroy</on_reboot>
        <on_crash>destroy</on_crash>
        <devices>
            <interface type="ethernet">
                <mac address="00:16:3E:5E:6C:00" />
                <ip address="10.137.0.1" />
                {extra_ip}
                <backenddomain name="test-inst-netvm" />
                <script path="vif-route-qubes" />
            </interface>
            <!-- server_ip is the address of stubdomain. It hosts it's own DNS server. -->
            <emulator type="stubdom-linux" />
            <input type="tablet" bus="usb"/>
            <video>
                <model type="vga"/>
            </video>
            <graphics type="qubes"/>
        </devices>
        </domain>
        '''
        my_uuid = '7db78950-c467-4863-94d1-af59806384ea'
        netvm = self.get_vm(qid=2, name='netvm', provides_network=True)
        vm = self.get_vm(uuid=my_uuid)
        vm.netvm = netvm
        vm.virt_mode = 'hvm'
        with self.subTest('ipv4_only'):
            libvirt_xml = vm.create_config_file()
            self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
                lxml.etree.XML(expected.format(extra_ip='')))
        with self.subTest('ipv6'):
            netvm.features['ipv6'] = True
            libvirt_xml = vm.create_config_file()
            self.assertXMLEqual(lxml.etree.XML(libvirt_xml),
                lxml.etree.XML(expected.format(
                    extra_ip='<ip address="{}::a89:1" family=\'ipv6\'/>'.format(
                        qubes.config.qubes_ipv6_prefix.replace(':0000', '')))))

    @unittest.mock.patch('qubes.utils.get_timezone')
    @unittest.mock.patch('qubes.utils.urandom')
    @unittest.mock.patch('qubes.vm.qubesvm.QubesVM.untrusted_qdb')
    def test_620_qdb_standalone(self, mock_qubesdb, mock_urandom,
            mock_timezone):
        mock_urandom.return_value = b'A' * 64
        mock_timezone.return_value = 'UTC'
        vm = self.get_vm(cls=qubes.vm.standalonevm.StandaloneVM)
        vm.netvm = None
        vm.events_enabled = True
        test_qubesdb = TestQubesDB()
        mock_qubesdb.write.side_effect = test_qubesdb.write
        mock_qubesdb.rm.side_effect = test_qubesdb.rm
        vm.create_qdb_entries()
        self.maxDiff = None

        iptables_header = (
            '# Generated by Qubes Core on {}\n'
            '*filter\n'
            ':INPUT DROP [0:0]\n'
            ':FORWARD DROP [0:0]\n'
            ':OUTPUT ACCEPT [0:0]\n'
            '-A INPUT -i vif+ -p udp -m udp --dport 68 -j DROP\n'
            '-A INPUT -m conntrack --ctstate '
            'RELATED,ESTABLISHED -j ACCEPT\n'
            '-A INPUT -p icmp -j ACCEPT\n'
            '-A INPUT -i lo -j ACCEPT\n'
            '-A INPUT -j REJECT --reject-with '
            'icmp-host-prohibited\n'
            '-A FORWARD -m conntrack --ctstate '
            'RELATED,ESTABLISHED -j ACCEPT\n'
            '-A FORWARD -i vif+ -o vif+ -j DROP\n'
            'COMMIT\n'.format(datetime.datetime.now().ctime()))

        self.assertEqual(test_qubesdb.data, {
            '/name': 'test-inst-test',
            '/type': 'StandaloneVM',
            '/default-user': 'user',
            '/qubes-vm-type': 'AppVM',
            '/qubes-debug-mode': '0',
            '/qubes-base-template': '',
            '/qubes-timezone': 'UTC',
            '/qubes-random-seed': base64.b64encode(b'A' * 64),
            '/qubes-vm-persistence': 'full',
            '/qubes-vm-updateable': 'True',
            '/qubes-block-devices': '',
            '/qubes-usb-devices': '',
            '/qubes-iptables': 'reload',
            '/qubes-iptables-error': '',
            '/qubes-iptables-header': iptables_header,
            '/qubes-service/qubes-update-check': '0',
        })

    @unittest.mock.patch('qubes.utils.get_timezone')
    @unittest.mock.patch('qubes.utils.urandom')
    @unittest.mock.patch('qubes.vm.qubesvm.QubesVM.untrusted_qdb')
    def test_621_qdb_vm_with_network(self, mock_qubesdb, mock_urandom,
            mock_timezone):
        mock_urandom.return_value = b'A' * 64
        mock_timezone.return_value = 'UTC'
        template = self.get_vm(cls=qubes.vm.templatevm.TemplateVM, name='template')
        template.netvm = None
        netvm = self.get_vm(cls=qubes.vm.appvm.AppVM, template=template,
            name='netvm', qid=2, provides_network=True)
        vm = self.get_vm(cls=qubes.vm.appvm.AppVM, template=template,
            name='appvm', qid=3)
        vm.netvm = netvm
        vm.kernel = None
        # pretend the VM is running...
        vm._qubesprop_xid = 3
        netvm.kernel = None
        test_qubesdb = TestQubesDB()
        mock_qubesdb.write.side_effect = test_qubesdb.write
        mock_qubesdb.rm.side_effect = test_qubesdb.rm
        self.maxDiff = None

        iptables_header = (
            '# Generated by Qubes Core on {}\n'
            '*filter\n'
            ':INPUT DROP [0:0]\n'
            ':FORWARD DROP [0:0]\n'
            ':OUTPUT ACCEPT [0:0]\n'
            '-A INPUT -i vif+ -p udp -m udp --dport 68 -j DROP\n'
            '-A INPUT -m conntrack --ctstate '
            'RELATED,ESTABLISHED -j ACCEPT\n'
            '-A INPUT -p icmp -j ACCEPT\n'
            '-A INPUT -i lo -j ACCEPT\n'
            '-A INPUT -j REJECT --reject-with '
            'icmp-host-prohibited\n'
            '-A FORWARD -m conntrack --ctstate '
            'RELATED,ESTABLISHED -j ACCEPT\n'
            '-A FORWARD -i vif+ -o vif+ -j DROP\n'
            'COMMIT\n'.format(datetime.datetime.now().ctime()))

        expected = {
            '/name': 'test-inst-appvm',
            '/type': 'AppVM',
            '/default-user': 'user',
            '/qubes-vm-type': 'AppVM',
            '/qubes-debug-mode': '0',
            '/qubes-base-template': 'test-inst-template',
            '/qubes-timezone': 'UTC',
            '/qubes-random-seed': base64.b64encode(b'A' * 64),
            '/qubes-vm-persistence': 'rw-only',
            '/qubes-vm-updateable': 'False',
            '/qubes-block-devices': '',
            '/qubes-usb-devices': '',
            '/qubes-iptables': 'reload',
            '/qubes-iptables-error': '',
            '/qubes-iptables-header': iptables_header,
            '/qubes-service/qubes-update-check': '0',
            '/qubes-ip': '10.137.0.3',
            '/qubes-netmask': '255.255.255.255',
            '/qubes-gateway': '10.137.0.2',
            '/qubes-primary-dns': '10.139.1.1',
            '/qubes-secondary-dns': '10.139.1.2',
        }

        with self.subTest('ipv4'):
            vm.create_qdb_entries()
            self.assertEqual(test_qubesdb.data, expected)

        test_qubesdb.data.clear()
        with self.subTest('ipv6'):
            netvm.features['ipv6'] = True
            expected['/qubes-ip6'] = \
                qubes.config.qubes_ipv6_prefix.replace(':0000', '') + \
                '::a89:3'
            expected['/qubes-gateway6'] = expected['/qubes-ip6'][:-1] + '2'
            vm.create_qdb_entries()
            self.assertEqual(test_qubesdb.data, expected)

        test_qubesdb.data.clear()
        with self.subTest('ipv6_just_appvm'):
            del netvm.features['ipv6']
            vm.features['ipv6'] = True
            expected['/qubes-ip6'] = \
                qubes.config.qubes_ipv6_prefix.replace(':0000', '') + \
                '::a89:3'
            del expected['/qubes-gateway6']
            vm.create_qdb_entries()
            self.assertEqual(test_qubesdb.data, expected)

        test_qubesdb.data.clear()
        with self.subTest('proxy_ipv4'):
            del vm.features['ipv6']
            expected['/name'] = 'test-inst-netvm'
            expected['/qubes-vm-type'] = 'NetVM'
            del expected['/qubes-ip']
            del expected['/qubes-gateway']
            del expected['/qubes-netmask']
            del expected['/qubes-ip6']
            del expected['/qubes-primary-dns']
            del expected['/qubes-secondary-dns']
            expected['/qubes-netvm-primary-dns'] = '10.139.1.1'
            expected['/qubes-netvm-secondary-dns'] = '10.139.1.2'
            expected['/qubes-netvm-network'] = '10.137.0.2'
            expected['/qubes-netvm-gateway'] = '10.137.0.2'
            expected['/qubes-netvm-netmask'] = '255.255.255.255'
            expected['/qubes-iptables-domainrules/3'] = \
                '*filter\n' \
                '-A FORWARD -s 10.137.0.3 -j ACCEPT\n' \
                '-A FORWARD -s 10.137.0.3 -j DROP\n' \
                'COMMIT\n'
            expected['/mapped-ip/10.137.0.3/visible-ip'] = '10.137.0.3'
            expected['/mapped-ip/10.137.0.3/visible-gateway'] = '10.137.0.2'
            expected['/qubes-firewall/10.137.0.3'] = ''
            expected['/qubes-firewall/10.137.0.3/0000'] = 'action=accept'
            expected['/qubes-firewall/10.137.0.3/policy'] = 'drop'

            with unittest.mock.patch('qubes.vm.qubesvm.QubesVM.is_running',
                    lambda _: True):
                netvm.create_qdb_entries()
            self.assertEqual(test_qubesdb.data, expected)

        test_qubesdb.data.clear()
        with self.subTest('proxy_ipv6'):
            netvm.features['ipv6'] = True
            ip6 = qubes.config.qubes_ipv6_prefix.replace(
                ':0000', '') + '::a89:3'
            expected['/qubes-netvm-gateway6'] = ip6[:-1] + '2'
            expected['/qubes-firewall/' + ip6] = ''
            expected['/qubes-firewall/' + ip6 + '/0000'] = 'action=accept'
            expected['/qubes-firewall/' + ip6 + '/policy'] = 'drop'
            with unittest.mock.patch('qubes.vm.qubesvm.QubesVM.is_running',
                    lambda _: True):
                netvm.create_qdb_entries()
            self.assertEqual(test_qubesdb.data, expected)
